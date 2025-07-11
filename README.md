# mlops-zoomcamp-epam
Repo for partaking in zoomcamp course with EPAM reviewing instructors

# Homework
- Week 1: [01-intro/homework.ipynb](01-intro/homework.ipynb)
- Week 2: [02-experiment-tracking/homework.ipynb](02-experiment-tracking/homework.ipynb)
- Week 3: [03-orchestration/README.md](03-orchestration/README.md)
- Week 4: [04-orchestration/README.md](04-orchestration/README.md)

# Note
Originally instructor recommended to use Anaconda, but I use [UV](https://github.com/astral-sh/uv), I find it generally better and convenient. Plus their Anaconda uses old or obsolete versions of packages.

Install from repo after `git clone`:
```shell
cd mlops-zoomcamp-epam
uv sync
```

Install from scratch without using repo config after `git clone`:
``` shell
cd mlops-zoomcamp-epam
uv init
uv add --dev ipykernel #if you use vscode for jupyter notes
uv add pandas seaborn matplotlib scikit-learn pyarrow
```

You may need to reload VS Code after this.