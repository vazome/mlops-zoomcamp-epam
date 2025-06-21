# mlops-zoomcamp-epam
Repo for partaking in zoomcamp course with EPAM reviewing instructors

Originally instructor recommended to use Anaconda, but I use [UV](https://github.com/astral-sh/uv), I find it generally better and convenient. Plus their Anaconda uses old or obsolete versions of packages.

``` shell
cd mlops-zoomcamp-epam
uv init
uv add --dev ipykernel
uv add pandas seaborn matplotlib scikit-learn pyarrow
```

You may need to reload VS Code after this.