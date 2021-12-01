from src.manage import Manage

if __name__=='__main__':
    manage = Manage()
    app_path = 'python_env/gui_program.py'
    try:
        manage.checkForUpdates()
        manage.startApp(app_path)
    except Exception as e:
        print(e)

