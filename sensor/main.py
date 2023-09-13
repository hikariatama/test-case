import datetime
import logging
import multiprocessing
import time

import requests
from data_source import generate_payload

logging.basicConfig(level=logging.INFO)


class Worker(multiprocessing.Process):
    def __init__(self, job_queue):
        super().__init__()
        self._job_queue = job_queue

    def run(self):
        while True:
            if (payload := self._job_queue.get()) is None:
                break

            requests.post("http://controller:8000/payload", json=payload)
            logging.debug("Sent payload %s to controller", payload)


def main():
    # Startup delay for the controller to start
    time.sleep(3)

    jobs = []
    job_queue = multiprocessing.Queue()

    for _ in range(5):
        p = Worker(job_queue)
        jobs.append(p)
        p.start()

    try:
        while True:
            payload = generate_payload()
            # Record the start time of the request in order to compensate for the
            # time it takes to send the request and actually make 300 requests per second
            start = time.perf_counter_ns()
            job_queue.put(
                {
                    "datetime": datetime.datetime.now().isoformat(),
                    "payload": payload,
                }
            )

            if (delay_correction := (time.perf_counter_ns() - start) / 1e9) < 1 / 300:
                time.sleep(1 / 300 - delay_correction)
    except KeyboardInterrupt:
        logging.info("Shutting down...")
        for _ in range(len(jobs)):
            job_queue.put(None)

        for job in jobs:
            job.join()


if __name__ == "__main__":
    main()
