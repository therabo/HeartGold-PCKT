import multiprocessing
import queue
import logging
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from configuration.manger_config import config

logger = logging.getLogger(__name__)


def database_writer_logic(results_queue: multiprocessing.Queue, num_workers: int):
    mongo_uri = config.database['Uri']
    db_name = config.database['DatabaseName']
    collection_name = config.database['CollectionGodPack']

    client = None
    try:
        logger.info("Process started. Connecting to MongoDB...")
        client = MongoClient(mongo_uri)
        db = client[db_name]
        collection = db[collection_name]
        logger.info("Successfully connected to MongoDB.")

        shutdown_signals_received = 0
        while shutdown_signals_received < num_workers:
            try:
                data = results_queue.get(timeout=1)

                if data is None:
                    shutdown_signals_received += 1
                    logger.info("Shutdown signal received (%d/%d).", shutdown_signals_received, num_workers)
                    continue

                if isinstance(data, dict) and data.get("type") == "update_level":
                    doc_id = data["doc_id"]
                    new_level = data["new_level"]
                    logger.info("Received level update for doc %s. Setting level to %d.", doc_id, new_level)
                    collection.update_one({"_id": doc_id}, {"$set": {"level": new_level}})
                else:
                    logger.info("Received new god pack document. Writing to DB...")
                    collection.insert_one(data)

            except queue.Empty:
                continue

        while not results_queue.empty():
            try:
                data = results_queue.get_nowait()
                if data is not None:
                    if isinstance(data, dict) and data.get("type") == "update_level":
                        doc_id = data["doc_id"]
                        new_level = data["new_level"]
                        collection.update_one({"_id": doc_id}, {"$set": {"level": new_level}})
                    else:
                        collection.insert_one(data)
            except queue.Empty:
                break

    except PyMongoError as e:
        logger.critical("FATAL MongoDB Error: %s", e)
    except Exception as e:
        logger.exception("An unhandled error occurred in the database writer: %s",e)
    finally:
        if client:
            client.close()
        logger.info("Queue is empty and all workers are done. Process terminated.")
