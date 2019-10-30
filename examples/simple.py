#!/usr/bin/env python

import os
import time
import logging
import executors
import argparse as ap
from executors.models import Job

logger = logging.getLogger(os.path.basename(__file__))
logging.basicConfig(level=logging.DEBUG)

def main():
    parser = ap.ArgumentParser()
    parser.add_argument('-p', '--partition', required=True)
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('command', nargs=ap.REMAINDER)
    args = parser.parse_args()
    
    if args.debug:
        logger.setLevel(logging.DEBUG)

    # get executor
    E = executors.probe(args.partition)

    # create a job 
    logger.info('building the job object')
    job = Job(
        command=['echo', 'Hello, World!'],
        memory='100M',
        time='10',
        name='simple',
        output='~/simple-%j.stdout',
        error='~/simple-%j.stderr'
    )

    # submit the job
    logger.info('submitting the job')
    E.submit(job)
    logger.info('job %s activity is %s', job.pid, job.active)
    
    # update the job object asyncronously
    logger.info('updating job %s object asyncronously', job.pid)
    E.update(job)
    logger.info('job %s activity is %s', job.pid, job.active)

    # now update the job syncronously
    logger.info('updating job %s object syncronously', job.pid)
    E.update(job, wait=True)
    logger.info('job %s activity is %s', job.pid, job.active)

    # now wait for job to finish
    logger.info('waiting for job %s to finish', job.pid)
    while True:
        E.update(job)
        if not job.active:
            logger.info('job %s returncode is %s', job.pid, job.returncode)
            break
        time.sleep(10)

if __name__ == '__main__':
    main()

