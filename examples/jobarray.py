#!/usr/bin/env python

import os
import time
import logging
import executors
import argparse as ap
from executors.models import Job,JobArray

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

    # get executors
    E = executors.probe(args.partition)

    # create a job 
    logger.info('building job #1')
    job1 = Job(
        name='job',
        command=['sleep', '30'],
        memory='100M',
        time='60',
        output='~/job-%j.stdout',
        error='~/job-%j.stderr'
    )

    # create another job and add it to the job array
    logger.info('building job #2')
    job2 = Job(
        name='job',
        command=['false'],
        memory='100M',
        time='10',
        output='~/job-%j.stdout',
        error='~/job-%j.stderr'
    )

    # create a job array and add the two jobs
    jobarray = JobArray(
        executor=E,
        cancel_on_fail=True
    )
    jobarray.add(job1)
    jobarray.add(job2)

    # run the job array
    jobarray.submit()
    jobarray.wait(wait=True)

if __name__ == '__main__':
    main()

