import configparser
import json
import re
import random
import multiprocessing
import logging

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
from configuration.manger_config import config
import operation_modules.collector as collector_module
import operation_modules.leveler as leveler_module
from operation_modules.database_writer import database_writer_logic
from network.proxy_manager import create_shared_ca_bundle, cleanup_shared_ca_bundle

logger = logging.getLogger(__name__)


class Director:
    def __init__(self):
        self.mongo_config = config.database
        self.pack_data_list = []
        self.is_data_loaded = False
        self.child_processes = []
        self.device_profiles = []
        self.writer_queue = multiprocessing.Queue()
        self.accounts_queue = multiprocessing.Queue()
        self.packs_opened_counter = multiprocessing.Value('i', 0)
        self.god_packs_found_counter = multiprocessing.Value('i', 0)
        self.leveler_progress_queue = multiprocessing.Queue()
        self.total_accounts_to_level = 0
        self.counter_lock = multiprocessing.Lock()
        self.writer_process = None
        self.start_all_collectors_event = multiprocessing.Event()
        self.shutdown_event = multiprocessing.Event()
        self.shared_ca_path = None
        if config.proxy_enabled:
            self.shared_ca_path = create_shared_ca_bundle()

        self.card_lookup_data = {}
        self.battle_lookup_data = {}
        self._load_card_lookup_data()
        self._load_battle_lookup_data()
        self._load_all_device_profiles()

    def _load_json_data(self, file_path: str) -> dict:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning("JSON file not found at '%s'.", file_path)
        except json.JSONDecodeError:
            logger.warning("Error decoding JSON from '%s'.", file_path)
        return {}

    def _load_card_lookup_data(self):
        self.card_lookup_data = self._load_json_data("cards/card_lookup.json")

    def _load_battle_lookup_data(self):
        self.battle_lookup_data = self._load_json_data("battle/battle_lookup.json")

    def _load_all_device_profiles(self):
        try:
            parser = configparser.ConfigParser()
            if not parser.read(config.user_agents_path):
                raise FileNotFoundError(f"File User-Agent non trovato: {config.user_agents_path}")
            for section_name in parser.sections():
                section = parser[section_name]
                user_agent = section['user_agent']
                os_match = re.search(r'Android OS (\d+)', user_agent)
                os_version = os_match.group(1) if os_match else "9"
                full_os_match = re.search(r'\((.*?)\)', user_agent)
                full_os_string = full_os_match.group(1) if full_os_match else "Android; Android OS 9 / API-28"
                profile_data = {
                    'device_name': section['model'],
                    'takasho_user_agent': user_agent,
                    'os_version': os_version,
                    'full_os_string': full_os_string
                }
                self.device_profiles.append(profile_data)
        except (FileNotFoundError, KeyError, configparser.Error) as e:
            print(f"Director WARNING: Could not load device profiles - {e}. Collectors may fail.")
            self.device_profiles = []

    def _get_director_db_uri(self):
        return self.mongo_config['Uri']

    def load_pack_data_from_db(self):
        if self.is_data_loaded:
            return True
        client = None
        try:
            client = MongoClient(self._get_director_db_uri(), serverSelectionTimeoutMS=5000)
            client.admin.command('ping')
            db = client[self.mongo_config['DatabaseName']]
            collection = db[self.mongo_config['CollectionPack']]
            projection = {"packId": 1, "packName": 1, "productId": 1, "coverPokemon": 1, "_id": 0}
            self.pack_data_list = [doc for doc in collection.find({}, projection) if
                                   all(k in doc for k in ["packName", "packId", "productId", "coverPokemon"])]
            if not self.pack_data_list:
                logger.warning("No valid pack data found in the database.")
            self.is_data_loaded = True
            logger.info("Successfully loaded %d pack configurations from database.", len(self.pack_data_list))
            return True
        except (ConnectionFailure, OperationFailure) as e:
            raise RuntimeError(f"Could not load pack data from MongoDB: {e}") from e
        finally:
            if client:
                client.close()

    def _load_accounts_for_leveling(self) -> int:
        logger.info("Loading accounts with level < 10 from database...")
        client = None
        try:
            client = MongoClient(self._get_director_db_uri(), serverSelectionTimeoutMS=5000)
            db = client[self.mongo_config['DatabaseName']]
            collection = db[self.mongo_config['CollectionGodPack']]

            accounts_to_level = list(collection.find({"level": {"$lt": 10}}))

            if not accounts_to_level:
                logger.info("Director: No accounts found with level < 10. Nothing to do.")
                self.total_accounts_to_level = 0
                return 0

            logger.info("Found %d accounts to level up. Populating queue...", len(accounts_to_level))
            for account in accounts_to_level:
                self.accounts_queue.put(account)

            self.total_accounts_to_level = len(accounts_to_level)
            return self.total_accounts_to_level

        except (ConnectionFailure, OperationFailure) as e:
            logger.exception("Could not load accounts from MongoDB. Leveling process cannot start.")
            self.total_accounts_to_level = 0
            return 0
        finally:
            if client: client.close()

    def _build_battle_playlist(self) -> list:
        battle_playlist = []
        difficulty_order = ["EXPERT", "ADVANCED", "INTERMEDIATE", "BEGINNER"]

        for difficulty in difficulty_order:
            battles_in_difficulty = self.battle_lookup_data.get(difficulty, {})
            if battles_in_difficulty:
                try:
                    sorted_battles = sorted(
                        battles_in_difficulty.items(),
                        key=lambda item: int(item[0].split('_')[1])
                    )
                    battle_playlist.extend(sorted_battles)
                except (ValueError, IndexError):
                    logger.warning("Could not sort battles for '%s'. Using default order.", difficulty)
                    battle_playlist.extend(battles_in_difficulty.items())

        if not battle_playlist:
            logger.warning("Battle playlist is empty. No battles found.")
        else:
            logger.info("Created a battle playlist with %d total battles.", len(battle_playlist))
        return battle_playlist

    def _start_database_writer(self, num_workers: int):
        if self.writer_process and self.writer_process.is_alive():
            return
        logger.info("Starting the Database Writer process.")
        self.writer_process = multiprocessing.Process(
            target=database_writer_logic,
            args=(self.writer_queue, num_workers)
        )
        self.writer_process.start()

    def _create_and_start_collector_process(self, assigned_pack_id: str, assigned_product_id: str, language_code: str,
                                            device_profile_data: dict):
        child_id = f"Collector_{assigned_pack_id}_{len(self.child_processes) + 1}"
        process = multiprocessing.Process(
            target=collector_module.collector_main_logic,
            args=(child_id, assigned_pack_id, assigned_product_id, language_code, device_profile_data)
        )
        self.child_processes.append(process)
        process.start()
        logger.info("Started child process %s (PID %d).", child_id, process.pid)

    def _create_and_start_leveler_process(self, child_id: str, device_profile_data: dict):
        process = multiprocessing.Process(
            target=leveler_module.leveler_main_logic,
            args=(child_id, device_profile_data)
        )
        self.child_processes.append(process)
        process.start()
        logger.info("Started child process %s (PID %d).", child_id, process.pid)

    def _inject_shared_data_for_collectors(self):
        collector_module.shared_data['start_event'] = self.start_all_collectors_event
        collector_module.shared_data['card_lookup_data'] = self.card_lookup_data
        collector_module.shared_data['results_queue'] = self.writer_queue
        collector_module.shared_data['shutdown_event'] = self.shutdown_event
        collector_module.shared_data['use_proxy'] = config.proxy_enabled
        collector_module.shared_data['shared_ca_path'] = self.shared_ca_path
        collector_module.shared_data['packs_opened_counter'] = self.packs_opened_counter
        collector_module.shared_data['god_packs_found_counter'] = self.god_packs_found_counter
        collector_module.shared_data['counter_lock'] = self.counter_lock

    def _inject_shared_data_for_levelers(self, battle_playlist: list):
        leveler_module.shared_data['accounts_queue'] = self.accounts_queue
        leveler_module.shared_data['shutdown_event'] = self.shutdown_event
        leveler_module.shared_data['use_proxy'] = config.proxy_enabled
        leveler_module.shared_data['shared_ca_path'] = self.shared_ca_path
        leveler_module.shared_data['battle_playlist'] = battle_playlist
        leveler_module.shared_data['writer_queue'] = self.writer_queue
        leveler_module.shared_data['progress_queue'] = self.leveler_progress_queue

    def orchestrate_collectors(self, assignments: list):
        num_collectors = sum(count for _, count, _ in assignments)
        if num_collectors == 0:
            logger.info("No Collectors assigned to be created. Exiting.")
            return

        self._start_database_writer(num_collectors)
        self._inject_shared_data_for_collectors()

        logger.info("Starting Collector child process creation...")
        for pack_info, count, lang_code in assignments:
            for _ in range(count):
                if not self.device_profiles:
                    logger.critical("No device profiles loaded. Cannot create collectors.")
                    return
                chosen_device_profile = random.choice(self.device_profiles)
                self._create_and_start_collector_process(
                    assigned_pack_id=pack_info['packId'],
                    assigned_product_id=pack_info['productId'],
                    language_code=lang_code,
                    device_profile_data=chosen_device_profile
                )
        self.signal_collectors_to_start()

    def orchestrate_levelers(self, num_processes: int):
        if num_processes <= 0:
            logger.info("No Leveler processes to create.")
            return

        battle_playlist = self._build_battle_playlist()
        if not battle_playlist:
            logger.error("Aborting Leveler start due to empty battle playlist.")
            return

        num_accounts = self._load_accounts_for_leveling()
        if num_accounts == 0:
            return

        num_levelers_to_start = min(num_accounts, num_processes)
        self._start_database_writer(num_levelers_to_start)
        self._inject_shared_data_for_levelers(battle_playlist)

        logger.info("Starting %d Leveler child processes...", num_levelers_to_start)
        for i in range(num_levelers_to_start):
            if not self.device_profiles:
                logger.critical("No device profiles loaded. Cannot create levelers.")
                return
            chosen_device_profile = random.choice(self.device_profiles)
            child_id = f"Leveler_{i + 1}"
            self._create_and_start_leveler_process(child_id, chosen_device_profile)

    def signal_collectors_to_start(self):
        if not self.child_processes:
            return
        logger.info("Sending START signal to all Collector processes...")
        self.start_all_collectors_event.set()

    def signal_shutdown(self):
        logger.info("SHUTDOWN SIGNAL RECEIVED. Notifying all processes to stop...")
        self.shutdown_event.set()

    def shutdown_and_wait(self):
        logger.info("Waiting for all child processes to finish...")
        num_children_to_signal = len(self.child_processes)
        for process in self.child_processes:
            process.join()
        self.child_processes = []
        logger.info("All child processes have terminated.")

        if self.writer_process and self.writer_process.is_alive():
            logger.info("Signaling writer to shut down by sending %d poison pills...", num_children_to_signal)
            for _ in range(num_children_to_signal):
                self.writer_queue.put(None)
            self.writer_process.join()
            logger.info("Database writer has shut down.")

        if self.shared_ca_path:
            cleanup_shared_ca_bundle(self.shared_ca_path)
