import random
from typing import Any


def generate_payload() -> Any:
    """
    Generates mock payload and returns the raw value of it
    :return: raw payload
    """
    return random.randint(-1000, 1000)
