import sys, os
from subprocess import call, check_output

try:
    if sys.version[0] == '2':
        try:
            print('Python 2 is default interpreter...going to try Python 3')
            py_check = check_output('where python').split('\r\n')
            py3_interpreter = ''.join([i for i in py_check if 'Python3' in i])
            the_call = py3_interpreter + ' ' + sys.argv[0]
            call(the_call)
        except Exception as e:
            print(e)
            raw_input('Hit enter to continue...')
    else:
        # Check if requests module is installed
        try:
            import requests
        except ModuleNotFoundError:
            call('python -m pip install requests', shell=False)
        from src.manage import Manage
        if __name__=='__main__':
            manage = Manage()
            app_path = './gui_program.py'
            try:
                manage.checkForUpdates()
                manage.startApp(app_path)
            except Exception as e:
                print(e)

except Exception as e:
    print(e)
    try:
        input('Hit enter...')
    except:
        raw_input('Hit enter...')
 