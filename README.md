# Cohat-Youtube-Manager  
Available at www.lcoats.me  

Serves as an alternative to the default youtube manager provided by google. 
There is never a need to enter sensitive data, as everything goes through google servers.  
If there is a 500 error, a good check is to skip to www.lcoats.me/authorize, (the error handler is strict, disable for debugging)
### Features:
- Windows version without threading, Linux version with celery tasks
- Downloading of mp4, conversion to mp3
- Conversion of channel title to channel id
- Mass specific and broad updates to titles and descriptions
- Viewing of any youtube channel and playlist in the same format
- Viewing choice of 50 embed youtube videos with selective loading
### Dependencies/Included Modules
- google-auth google-auth-oauthlib google-auth-httplib2
- flask
- requests
- pytube
- celery (in linux version, it is possible to replace with old windows version)
- redis server used by celery
- ffmpeg (app uses ffmpeg in env variables by default)
- YouTube credentials: api key, 2.0 client id's client_secret.json
### How To Use
- Add client_secret.json, replace api_key and flask_secret key(can be anything secure) in keyfile.py 
- Install ffmpeg (change loc_ffmpeg location in keyfile.py to install location/or set environmental variables path)
- Create/update venv
- Run uvideomanager.py or (uvideomanager_linuxbackground.py if on linux server)
#### "Why'd you do it this way?"
- The general answer is 'I didn't know any better'
- I used Celery because it was well documented. Although it used to be supported for windows, there are many issues with that version.
- The Ajax polling solution messes with the architecture I originally had
### Example Image of One Video
<img src="https://github.com/coatsandhats/Cohat-Youtube-Manager/blob/master/example1.PNG" width="600" height="300">
