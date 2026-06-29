import os
import multiprocessing
import time
import threading
import sys

os.environ['GRPC_VERBOSITY'] = 'NONE'
os.environ['GRPC_TRACE'] = ''

from pathlib import Path

GENERATED_PROTO_DIR = Path(__file__).resolve().parent / "protobuf" / "generated"
if str(GENERATED_PROTO_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATED_PROTO_DIR))

from rich.live import Live
from rich.console import Group
from rich.align import Align
from rich.panel import Panel
from rich.padding import Padding
import queue

from operation_modules.director import Director
from configuration.logging_config import setup_logging
from ui import console


def wait_for_enter(stop_event: threading.Event):
    input()
    stop_event.set()


def main():
    console.display_initial_screen()
    console.console.print()
    setup_logging()
    try:
        director_instance = Director()
        choice = console.ask_main_menu_choice()

        if choice is None or choice == "exit":
            print("\n[*] Exiting HeartGold-PCKT. Goodbye!")
            return 0

        if choice == "leveler":
            num_levelers = console.ask_leveler_process_count()
            if num_levelers is None or num_levelers == 0:
                print("\n[*] No Levelers to create. Exiting.")
                return 0

            if not console.confirm_start(f"Do you want to start the Leveler with {num_levelers} processes?"):
                print("\n[*] Start cancelled by user.")
                return 0

            director_instance.orchestrate_levelers(num_levelers)

            total_accounts = director_instance.total_accounts_to_level
            if total_accounts == 0:
                print("\n[*] No accounts found that require leveling. Exiting.")
                return 0

            summary_table = console.display_leveler_summary_table(total_accounts)
            banner_panel = console.get_banner_panel()
            completed_count = 0

            with Live(console=console.console, screen=True, redirect_stderr=False, vertical_overflow="visible",
                      transient=True) as live:
                try:
                    while completed_count < total_accounts:
                        try:
                            director_instance.leveler_progress_queue.get(timeout=1)
                            completed_count += 1
                        except queue.Empty:
                            pass

                        stats_panel = console.generate_leveler_stats_table(completed_count, total_accounts)

                        tables_group = Group(
                            Padding(summary_table, (1, 0, 0, 0)),
                            Padding(stats_panel, (1, 0, 0, 0))
                        )

                        main_content = Group(
                            banner_panel,
                            Align.center(tables_group)
                        )

                        live.update(Align(main_content, align="left"))
                        time.sleep(0.1)

                except KeyboardInterrupt:
                    print("\n[!] Keyboard interrupt received. Shutting down...")
                    director_instance.signal_shutdown()

            final_stats_panel = console.generate_leveler_stats_table(completed_count, total_accounts)
            completed_panel = Panel(
                Align.center("[bold green]All accounts have been processed![/bold green]"),
                border_style="green",
                expand=True
            )

            final_group = Group(
                banner_panel,
                Align.center(Group(
                    Padding(summary_table, (1, 0, 0, 0)),
                    Padding(final_stats_panel, (1, 0, 0, 0)),
                    Padding(completed_panel, (1, 0, 0, 0))
                ))
            )

            console.console.print(Align(final_group, align="left"))

            director_instance.shutdown_and_wait()
            print("[*] Operations completed.")
            return 0

        elif choice == "collector":
            director_instance.load_pack_data_from_db()
            pack_list = director_instance.pack_data_list
            if not pack_list:
                console.console.print("[!] No pack data loaded from the DB. Exiting.")
                return 1

            num_children_to_create = console.ask_collector_process_count()
            if num_children_to_create is None or num_children_to_create == 0:
                print("\n[*] No Collectors to create. Exiting.")
                return 0

            language_options = {"it": "Italiano", "en": "English", "jp": "Japanese"}
            assignments = console.ask_for_assignments(pack_list, language_options, num_children_to_create)

            if not assignments:
                print("\n[*] No assignments created. Exiting.")
                return 0

            summary_table = console.display_assignment_summary_table(assignments, language_options)
            console.console.print(summary_table)

            if console.confirm_start():
                director_instance.orchestrate_collectors(assignments)
            else:
                print("\n[*] Start cancelled by user.")
                return 0

        if not director_instance.child_processes:
            print("\n[*] No child processes were started.")
            return 0

        stop_event = threading.Event()
        input_thread = threading.Thread(target=wait_for_enter, args=(stop_event,), daemon=True)
        input_thread.start()

        banner_panel = console.get_banner_panel()

        with Live(console=console.console, screen=True, redirect_stderr=False, vertical_overflow="visible") as live:
            last_check_time = time.time()
            last_pack_count = 0

            try:
                while not stop_event.is_set():
                    current_time = time.time()
                    with director_instance.counter_lock:
                        current_pack_count = director_instance.packs_opened_counter.value
                        current_god_pack_count = director_instance.god_packs_found_counter.value

                    delta_time = current_time - last_check_time
                    delta_packs = current_pack_count - last_pack_count
                    packs_per_minute = (delta_packs / delta_time) * 60 if delta_time > 1 else 0

                    stats_panel = console.generate_stats_table(
                        current_pack_count,
                        current_god_pack_count,
                        packs_per_minute
                    )

                    tables_group = Group(
                        Padding(summary_table, (1, 0, 0, 0)),
                        Padding(stats_panel, (1, 0, 0, 0))
                    )

                    main_content = Group(
                        banner_panel,
                        Align.center(tables_group)
                    )

                    live.update(Align(main_content, align="left"))

                    last_check_time = time.time()
                    last_pack_count = current_pack_count
                    time.sleep(2)

            except KeyboardInterrupt:
                pass
            else:
                pass

            director_instance.signal_shutdown()

            shutdown_panel = Panel(
                "[bold yellow]Shutdown in progress... Waiting for all processes to finish.[/bold yellow]")

            shutdown_content = Group(
                banner_panel,
                Align.center(shutdown_panel)
            )

            live.update(Align(shutdown_content, align="left"))

            director_instance.shutdown_and_wait()

        print("[*] Operations completed.")
        return 0

    except (RuntimeError, FileNotFoundError, KeyError) as e:
        console.console.print(f"\n[bold red]FATAL Error: {e}[/bold red]")
        return 1
    except Exception as e:
        console.console.print(f"\n[bold red]FATAL Unexpected Error:[/bold red]")
        console.console.print_exception()
        return 1


if __name__ == "__main__":
    if sys.platform != 'win32' and sys.platform != 'darwin':
        try:
            multiprocessing.set_start_method('fork')
        except RuntimeError:
            pass
    sys.exit(main())
