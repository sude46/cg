import os


def child_exit(server, worker):
    if os.getenv('PROMETHEUS_MULTIPROC_DIR'):
        from prometheus_client import multiprocess

        multiprocess.mark_process_dead(worker.pid)
