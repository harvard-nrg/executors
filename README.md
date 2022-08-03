Executors
=========
Software needs to be smart enough to adapt to the execution environment without needing 
much input from the end user. At its core, Executors settles on a small set of high-level 
operations e.g., `submit`, `update` (query), and `cancel` that seem to map quite well 
across different computing environments. If you need to run your command on a local machine, 
Slurm, LSF, or some futuristic execution environment, `executors` can do it!

## Table of contents
1. [Installation](#installation)
2. [Supported job schedulers](#supported-job-schedulers)
3. [Usage](#usage)
   * [instantiate an executor](#instantiate-an-executor)
   * [instantiate a job](#instantiate-a-job)
   * [submit the job](#submit-the-job)
   * [update the job state](#update-the-job-state)
   * [update many job states](#update-many-job-states)
4. [Job arrays](#job-arrays)
5. [Extending Executors](#extending-executors)

## Installation
Just use pip

```bash
pip install executors
```

## Supported job schedulers
The following job schedulers are supported

* `slurm` - Simple Linux Utility for Resource Management
* `lsf` - IBM Platform LSF
* `pbsubmit` - Martinos Center Torque wrapper
* `local` - Local job executor

## Usage
The goal is to keep this section as small as possible to get you up and running 
as quickly as possible. Here we go!

### instantiate an `Executor`
To start using Executors, you need to instantiate an `Executor` object. You can 
do this in one of two ways. First, you can use `executors.probe` to 
automatically discover the job scheduler present in your environment

```python
import executors

E = executors.probe('partition_name')
```

Alternatively, you can explicitly load an `Executor` using `executors.get`, 
passing in the type of scheduler as the first argument

```python
import executors

E = executors.get('local')
```

Note that for schedulers other than `local`, you will need to pass in a second 
argument called `partition_name`. This referred to as a `queue` in some job 
schedulers

```python
import executors

E = executors.get('slurm', 'partition_name')
```

### instantiate a `Job`
Next, you have to create a `Job`. See below for descriptions of the supported 
arguments

```python
from executors.models import Job

job = Job(
    name='job',
    command=['echo', 'Hello, World!'],
    memory='100M',
    time='10',
    output='~/job-%j.stdout',
    error='~/job-%j.stderr'
)
```

* `name`: Job name (required)
* `command`: Command to be executed (required)
* `memory`: Amount of memory to reserve e.g., `1000K`, `100M`, `10G`, `1TB` (required)
* `time`: Amount of time to reserve, in seconds (required)
* `cpus`: Number of processors to reserve (default=1)
* `nodes`: Number of nodes to reserve (default=1)
* `output`: Path to standard output. Any occurrence of `%j` will be replaced with Job ID.
* `error`: Path to standard error. Any occurrence of `%j` will be replaced with Job ID.
* `parent`: Parent job object a.k.a job dependency.

### submit the `Job`
Now you can submit your `job` using your executor object `E`. Once the job has 
been submitted, the `job.pid` property will be set

```python
E.submit(job)
print(f'the job id is {job.pid}')
```

When the job finishes, you can check it's `returncode`

```python
print(f'the job returncode is {job.returncode}')

```

### updating the `Job` state
Each `Job` has `active` and `returncode` properties. By default, these are 
both set to `None`. These properties will be updated every time you call 
`E.update(job)`

```python
E.update(job)
print(f'job {job.pid} has state {job.active} and returncode {job.returncode}')
```

Keep in mind that even though you have submitted a job, you may not be able to 
immediately query its state. For this reason, Executors cannot *guarantee* that 
calling `E.update` will update your `Job` state. If you want `E.update` to wait 
until a job is able to be queried, add the argument `wait=True`

```python
E.update(job, wait=True)
```

### update many `Job` states
Some job schedulers offer efficient ways to query the state of multiple jobs. 
For that reason, if you have a `list` (or `generator`) of `Job` objects, 
you can pass those to the `update_many` method

```python
E.update_many(jobs)
```

> Some `Executor` objects optimize how `update_many` is fulfilled, while others 
> will resort to serially querying one job after the other which could result in 
> poor performance.

# Job arrays
There are times when you may want to submit several related jobs and control 
them as a group. A common need is to cancel all remaining jobs if any single job 
has failed. This is precisely what the `JobArray` class is for. Let's take a look 
at an example

```python
from executors.models import JobArray

jobarray = JobArray(
    executor=E,
    cancel_on_fail=True
)
jobarray.add(job_a)
jobarray.add(job_b)
jobarray.submit()
jobarray.wait()
```

To impose rate limiting on the number of jobs submitted concurrently, use the 
`limit` argument. For example, use `limit=1` to have only 1 job running at a 
time

```python
jobarray.submit(limit=1)
```

## Extending Executors
It's fairly simple to extend Executors as you encounter new schedulers. First 
you must create a new module within the top-level `executors` module, for example

```bash
executors/awsbatch/__init__.py
```

Next, within this module, you must create a new `Executor` class that extends 
`executors.models.AbstractExecutor`

```python
from executors.models import AbstractExecutor

class Executor(AbstractExecutor):
    ...
```

Finally you need to add your executor to the `probe` and `get` functions within 
`executors/__init__.py`.
