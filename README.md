
###Setting up new computer:

1. cd to directory.
2. make sure python and pip are installed on device - and that PATH is defined for both in windows environment variables.
3. run pip install virtualenv
4. Then virtualenv <environment name>
5. Make sure to update the requirements.txt file with the packages installed in the environment by using pip freeze > requirements.txt
6. Use pip install -r requirements.txt to install all pip packages for new environment
8. Create .env file in new device root directory - and add the slack bot token


###Heroku

1. Make sure Heroku CLI is downloaded on device
2. run heroku update
3. heroku login
4. heroku create (If the heroku app has not been created already)
5. git push heroku master (master is the branch name)
6. Setup needed environment variables
7. Make sure Procfile has been created - and that it contains a name for the app so that you can run it continously on heroku
8. Then heroku ps:scale web=1 (worker/web here will depend on the name you choose on the Procfile)



