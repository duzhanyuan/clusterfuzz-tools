package(default_visibility = ["//visibility:public"])


load("@io_bazel_rules_pex//pex:pex_rules.bzl", "pex_binary")
load('//tool:requirements.bzl', 'prod_requirements')


pex_binary(
    name='clusterfuzz',
    main='clusterfuzz/main.py',
    deps=[':bare'],
    reqs=prod_requirements,
    # zip_safe=False unzips the pex file before running. This enables more
    # flexibility when using a resource file (e.g. executing it with bash).
    # This is the reason why we choose pex over subpar.
    zip_safe=False,
)


py_library(
    name='src',
    deps=[':bare', '@dev_tool_requirements//:libraries']
)


py_library(
    name='bare',
    srcs=glob(['clusterfuzz/**/*.py']),
    data=glob(['clusterfuzz/resources/**/*']),
)


py_test(
    name='test',
    srcs=['run_test.py'] + glob(['tests/**/*_test.py']),
    deps=[':src', '//:shared'],
    main='run_test.py',
    local=1
)

