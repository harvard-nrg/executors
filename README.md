Executors
=========
If you want to write scripts that work transparently across different job 
schedulers, things can get weird, and it's easy to find yourself locked into 
a specific job scheduler. Executors tries to eliminate this challenge. Just 
tell Executors to run a command and it will run it on whatever is available.

Each scheduler within Executors will expose methods to `submit`, `update`, and 
`cancel` a job. With these methods, you can build fairly sophisticated tools 
quickly. If you need to run on your local machine today, Slurm tomorrow, and 
LSF next week, you don't need to change anything. 

Executors also provides a special `JobArray` class for building and managing 
collections of jobs as a single object. There are no restrictionson the size 
or shape of jobs that you can add to a `JobArray`. You can also setup 
convenient behaviors such as killing all remaining jobs if a single job fails.

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
schedulers.

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
    cpus=1,
    nodes=1,
    output='~/job-%j.stdout',
    error='~/job-%j.stderr',
    parent=parent
)
```

* `name`: Job name (required)
* `command`: Command to be executed (required)
* `memory`: Amount of memory required e.g., `1000K`, `100M`, `10G`, `1TB` (required)
* `time`: Amount of time required in seconds (required)
* `cpus`: Number of processors needed (default=1)
* `nodes`: Number of nodes needed (default=1)
* `output`: Path to standard output. Any occurrence of `%j` will be replaced with Job ID.
* `error`: Path to standard error. Any occurrence of `%j` will be replaced with Job ID.
* `parent`: Parent job object a.k.a job dependency.

### submit the `Job`
Now you can submit your `job` using your executor object `E`. Once the job has 
been submitted, the `job.pid` property will be set

```python
E.submit(job)
print('the job id is {0}'.format(job.pid))
```

When the job finishes, you can check it's `returncode`.

### updating the `Job` state
Each `Job` has an `active` and `returncode` property. By default, these are 
both set to `None`. These properties will be updated each time you call 
`E.update(job)`

```python
E.update(job)
print('job {0} has state {1} and returncode is {2}'.format(job.pid, job.active, job.returncode))
```

> Some job schedulers will allow you to submit a job but you cannot instantly 
> begin querying the job state, therefore Executors cannot always *guarantee* that 
> `E.update` will update the `Job` state. If you must have `E.update` wait until 
> a job is visible, add the argument `wait=True`.

### update many `Job` states
Some job schedulers offer more efficient ways to query the state of multiple 
jobs. For that reason, if you have a `list` or `generator` of `Job` objects, 
you can pass those to the `update_many` method

```python
E.update_many(jobs)
```

> Some `Executor` objects can optimize how `update_many` is fulfilled, others 
> will resort to serially querying one job after the other. This could cause 
> a linear slow down.

# Job arrays
There are times when you want to submit several related jobs and control them 
as a group. A common need is to cancel remaining jobs if any single job has 
failed. This is what the `JobArray` class is for. Let's give it a whirl

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

To impose rate limiting on the number of jobs running concurrently, use the 
`limit` argument. For example, to only have 1 job running at a time

```python
jobarray.submit(limit=1)
```

## Extending Executors
It's fairly simple to extend Executors as you encounter new schedulers. First 
you must create a new module within the top-level `executors` module, for example

```bash
executors/awsbatch/__init__.py
```

Now, within this module you must create a new `Executor` class that extends 
`executors.models.AbstractExecutor`

```python
from executors.models import AbstractExecutor

class Executor(AbstractExecutor):
    ...
```

Finally you need to add your executor to the `probe` and `get` functions within 
`executors/__init__.py`.
