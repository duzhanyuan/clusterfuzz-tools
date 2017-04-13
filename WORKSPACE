git_repository(
    name = "io_bazel_rules_pex",
    remote = "https://github.com/tanin47/bazel_rules_pex.git",
    tag = "0.3.0",
)


load('//build_tools:pypi.bzl', 'pip', 'pip_requirements')
load('//tool:requirements.bzl', 'prod_requirements', 'dev_requirements')
pip()
pip_requirements(
    name='prod_tool_requirements',
    packages=prod_requirements
)
pip_requirements(
    name='dev_tool_requirements',
    packages=dev_requirements + prod_requirements
)

load("@io_bazel_rules_pex//pex:pex_rules.bzl", "pex_repositories")
pex_repositories()

