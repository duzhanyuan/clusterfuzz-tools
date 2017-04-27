
import cmd

result = {}
result[cmd.InputInvoke('test')] = 'yes'

print result[cmd.InputInvoke('test')]
