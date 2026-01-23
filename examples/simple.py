#!/usr/bin/env python

import os
import sys
import time
import logging
import executors
import argparse as ap
from executors.models import Job

logger = logging.getLogger(os.path.basename(__file__))
logging.basicConfig(level=logging.DEBUG)

def main():
    parser = ap.ArgumentParser()
    parser.add_argument('-s', '--scheduler')
    parser.add_argument('-p', '--partition', required=True)
    parser.add_argument('-m', '--mem', default='100M')
    parser.add_argument('-t', '--time', default=10)
    parser.add_argument('-n', '--name', default='example')
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('command', nargs=ap.REMAINDER)
    args = parser.parse_args()
    
    if args.debug:
        logger.setLevel(logging.DEBUG)

    if not args.command:
        logger.critical('did you forget to pass a command?')
        sys.exit(1)

    # get executor
    if args.scheduler:
        E = executors.get(args.scheduler, args.partition)
    else:
        E = executors.probe(args.partition)

    # create a job 
    logger.info('building a job object')
    job = Job(
        command=args.command,
        memory=args.mem,
        time=str(args.time),
        name=args.name,
        output=f'{args.name}-%j.stdout',
        error=f'{args.name}-%j.stderr'
    )

    # submit the job
    logger.info('submitting the job')
    E.submit(job)
    logger.info(f'job {job.pid} activity is {job.active}')
    
    # update the job object asyncronously
    logger.info(f'updating job {job.pid} object asyncronously')
    E.update(job)
    logger.info(f'job {job.pid} activity is {job.active}')

    # now update the job syncronously
    logger.info(f'updating job {job.pid} object syncronously')
    E.update(job, wait=True)
    logger.info(f'job {job.pid} activity is {job.active}')

    # now wait for job to finish
    logger.info(f'waiting for job {job.pid} to finish')
    while True:
        E.update(job)
        if not job.active:
            logger.info(f'job {job.pid} returncode is {job.returncode}')
            break
        time.sleep(10)

if __name__ == '__main__':
    main()

