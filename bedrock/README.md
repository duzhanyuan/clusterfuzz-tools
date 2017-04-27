Bedrock - A functional programming framework for a command-line tool
=====================================================================

One of the problems we encounter with our clusterfuzz tools is checking all
dependencies before running anything else. Here are some examples:

* The tool builds Chrome for 15 minutes and, later, fails because `blackbox` is not installed.
* The tool downloads a testcase for 5 minutes and, later, ask if user wants to perform `git checkout`.

It would be better to ask for user input and check every dependency upfront;
User can run, answer all questions, and leave it.

Bedrock solves this problem.

