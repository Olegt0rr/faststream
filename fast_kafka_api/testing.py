# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/999_Test_Utils.ipynb.

# %% auto 0
__all__ = ['logger', 'kafka_server_url', 'kafka_server_port', 'kafka_config', 'true_after', 'create_missing_topics',
           'create_testing_topic', 'create_and_fill_testing_topic', 'nb_safe_seed', 'mock_AIOKafkaProducer_send',
           'change_dir', 'run_script_and_cancel']

# %% ../nbs/999_Test_Utils.ipynb 1
import asyncio
import contextlib
import hashlib
import os
import random
import shlex

# [B404:blacklist] Consider possible security implications associated with the subprocess module.
import subprocess  # nosec
import time
import unittest
import unittest.mock
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple, AsyncIterator

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from confluent_kafka.admin import AdminClient, NewTopic

from ._components.logger import get_logger

# %% ../nbs/999_Test_Utils.ipynb 3
logger = get_logger(__name__)

# %% ../nbs/999_Test_Utils.ipynb 5
kafka_server_url = (
    os.environ["KAFKA_HOSTNAME"] if "KAFKA_HOSTNAME" in os.environ else "localhost"
)
kafka_server_port = os.environ["KAFKA_PORT"] if "KAFKA_PORT" in os.environ else "9092"

kafka_config = {
    "bootstrap.servers": f"{kafka_server_url}:{kafka_server_port}",
    # "group.id": f"{kafka_server_url}:{kafka_server_port}_group"
}

# %% ../nbs/999_Test_Utils.ipynb 6
def true_after(seconds: float) -> Callable[[], bool]:
    """Function returning True after a given number of seconds"""
    t = datetime.now()

    def _true_after(seconds: float = seconds, t: datetime = t) -> bool:
        return (datetime.now() - t) > timedelta(seconds=seconds)

    return _true_after

# %% ../nbs/999_Test_Utils.ipynb 8
## TODO: Check if replication num is <= of number of brokers
## TODO: Add tests for:
#             - Replication factor (less than and greater than number of brokers)
#             - Num partitions


def create_missing_topics(  # type: ignore
    admin: AdminClient,
    topic_names: List[str],
    *,
    num_partitions: Optional[int] = None,
    replication_factor: Optional[int] = None,
    **kwargs,
) -> None:
    if not replication_factor:
        replication_factor = len(admin.list_topics().brokers)
    if not num_partitions:
        num_partitions = replication_factor
    existing_topics = list(admin.list_topics().topics.keys())
    logger.debug(
        f"create_missing_topics({topic_names}): existing_topics={existing_topics}, num_partitions={num_partitions}, replication_factor={replication_factor}"
    )
    new_topics = [
        NewTopic(
            topic,
            num_partitions=num_partitions,
            replication_factor=replication_factor,
            **kwargs,
        )
        for topic in topic_names
        if topic not in existing_topics
    ]
    if len(new_topics):
        logger.info(f"create_missing_topics({topic_names}): new_topics = {new_topics}")
        fs = admin.create_topics(new_topics)
        while not set(topic_names).issubset(set(admin.list_topics().topics.keys())):
            time.sleep(1)

# %% ../nbs/999_Test_Utils.ipynb 10
@contextmanager
def create_testing_topic(
    kafka_config: Dict[str, Any], topic_prefix: str, seed: Optional[int] = None
) -> Generator[str, None, None]:
    # create random topic name
    random.seed(seed)
    # [B311:blacklist] Standard pseudo-random generators are not suitable for security/cryptographic purposes.
    suffix = str(random.randint(0, 10**10))  # nosec

    topic = topic_prefix + suffix.zfill(3)

    # delete topic if it already exists
    admin = AdminClient(kafka_config)
    existing_topics = admin.list_topics().topics.keys()
    if topic in existing_topics:
        logger.warning(f"topic {topic} exists, deleting it...")
        fs = admin.delete_topics(topics=[topic])
        results = {k: f.result() for k, f in fs.items()}
        while topic in admin.list_topics().topics.keys():
            time.sleep(1)
    try:
        # create topic if needed
        create_missing_topics(admin, [topic])
        while topic not in admin.list_topics().topics.keys():
            time.sleep(1)
        yield topic

    finally:
        pass
        # cleanup if needed again
        fs = admin.delete_topics(topics=[topic])
        while topic in admin.list_topics().topics.keys():
            time.sleep(1)

# %% ../nbs/999_Test_Utils.ipynb 12
@asynccontextmanager
async def create_and_fill_testing_topic(
    msgs: List[bytes], kafka_config: Dict[str, str] = kafka_config, *, seed: int
) -> AsyncIterator[str]:

    with create_testing_topic(kafka_config, "my_topic_", seed=seed) as topic:

        producer = AIOKafkaProducer(bootstrap_servers=kafka_config["bootstrap.servers"])
        logger.info(f"Producer {producer} created.")

        await producer.start()
        logger.info(f"Producer {producer} started.")
        try:
            fx = [
                producer.send(
                    topic,
                    msg,
                    key=f"{i % 17}".encode("utf-8"),
                )
                for i, msg in enumerate(msgs)
            ]
            await producer.flush()
            sent_msgs = [await f for f in fx]
            msg_statuses = [await s for s in sent_msgs]
            logger.info(f"Sent messages: len(sent_msgs)={len(sent_msgs)}")

            yield topic
        finally:
            await producer.stop()
            logger.info(f"Producer {producer} stoped.")

# %% ../nbs/999_Test_Utils.ipynb 15
def nb_safe_seed(s: str) -> Callable[[int], int]:
    """Gets a unique seed function for a notebook

    Params:
        s: name of the notebook used to initialize the seed function

    Returns:
        A unique seed function
    """
    init_seed = int(hashlib.sha256(s.encode("utf-8")).hexdigest(), 16) % (10**8)

    def _get_seed(x: int = 0, *, init_seed: int = init_seed) -> int:
        return init_seed + x

    return _get_seed

# %% ../nbs/999_Test_Utils.ipynb 17
@contextmanager
def mock_AIOKafkaProducer_send() -> Generator[unittest.mock.Mock, None, None]:
    """Mocks **send** method of **AIOKafkaProducer**"""
    with unittest.mock.patch("__main__.AIOKafkaProducer.send") as mock:

        async def _f():
            pass

        mock.return_value = asyncio.create_task(_f())

        yield mock

# %% ../nbs/999_Test_Utils.ipynb 18
@contextlib.contextmanager
def change_dir(d: str) -> Generator[None, None, None]:
    curdir = os.getcwd()
    os.chdir(d)
    try:
        yield
    finally:
        os.chdir(curdir)

# %% ../nbs/999_Test_Utils.ipynb 20
def run_script_and_cancel(
    *, script: str, script_file: str, cmd: str, cancel_after: int
) -> bytes:
    with TemporaryDirectory() as d:
        consumer_script = Path(d) / script_file

        with open(consumer_script, "a+") as file:
            file.write(script)

        # os.chdir(d)
        with change_dir(d):
            proc = subprocess.Popen(  # nosec: [B603:subprocess_without_shell_equals_true] subprocess call - check for execution of untrusted input.
                shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )
            time.sleep(cancel_after)
            proc.terminate()
            proc.wait()

        return proc.stdout.read()  # type: ignore
