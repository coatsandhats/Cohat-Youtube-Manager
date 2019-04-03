import sys
import flask
import time
import requests
import subprocess
import keyfile
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
from pytube import YouTube
from flask import Markup, request, render_template, send_file
from tasks import make_celery
from celery.result import AsyncResult

CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'

app = flask.Flask(__name__)
app.secret_key = keyfile.flask_secret_key
app.config.update(
    CELERY_BROKER_URL='redis://localhost:6379/0',
    CELERY_RESULT_BACKEND='redis://localhost:6379/0'
)
celery = make_celery(app)

@app.before_first_request
def init_app():
    flask.session['is_other_channel'] = False
    flask.session['channel_id'] = ''
    flask.session['channel_page_num'] = 0
    flask.session['playlist_page_num'] = 0
    flask.session['playlist_num'] = 0
    flask.session['v_id'] = ''
    flask.session['id'] = ''
    flask.session['test'] = False

@app.route('/error/')
@app.errorhandler(500)
def reroute(e):
    init_app()
    return flask.redirect('authorize')

@app.route('/check')
def check():
    print('check')
    flask.session['test'] = False
    res = AsyncResult(flask.session['id'])
    if res.ready() is True:
        flask.session['test'] = True
        return 'true'
    else:
        return 'false'

@app.route('/send')
def send():
    if flask.session['test'] is True:
        print('yeo')
        flask.session['test'] = False
        res = AsyncResult(flask.session['id'])
        result = res.get()
        res.revoke()
        return send_file(result, as_attachment=True)
    else:
        return '', 204

# website interaction after render will be with a prefix of index_. Html render with prefix of my_
@app.route('/')
def my_form():
    client = get_client()
    if (flask.session.get('channel_id') and flask.session.get('is_other_channel') and flask.session.get('channel_page_num')) is None:
        init_app()
        return flask.redirect('authorize')
    channel_id = flask.session['channel_id']
    is_other_channel = flask.session['is_other_channel']
    first_channel_page_num = flask.session['channel_page_num']
    # Decide whether to render 'Mine' or channel_id by the boolean is_other_channel
    if is_other_channel:
        uploads_list = get_uploads(client, first_channel_page_num,
                                   id=channel_id,
                                   part='contentDetails',
                                   maxResults=50
                                   )
        playlists = get_playlists(client,
                                  id=channel_id,
                                  part='contentDetails',
                                  maxResults=50
                                  )
        try:
            channel = client.channels().list(
                    part="snippet",
                    id=channel_id,
            ).execute()
        except:
            flask.session['is_other_channel'] = False
            return flask.redirect(flask.url_for('my_form'))
    else:
        uploads_list = get_uploads(client, first_channel_page_num,
                                       mine=True,
                                       part='contentDetails',
                                       maxResults=50
                                       )
        playlists = get_playlists(client,
                                      mine=True,
                                      part='contentDetails',
                                      maxResults=50
                                      )
        channel = client.channels().list(
                    part="snippet",
                    mine=True,
        ).execute()
    username = channel['items'][0]["snippet"]["title"]
    fixed_channel_page_num = flask.session['channel_page_num']
    if not is_other_channel:
        all_forms = Markup(f"""<hr><button class='show'>Show Append Forms</button><form method="POST" id="form" name='form'>
        <div class="append">
        Enter full append top of description(return for line break):
            <textarea name="appendtop"></textarea> <span style="position: absolute; margin-left: 200px;">*Anything entered in these boxes will be used when updating page*</span>
            <br />
        Enter full append bottom of description(return for line break):
            <textarea name="appendbottom"></textarea>
            <br />
        Enter phrase to be deleted(*warning):
            <textarea name="replace"></textarea>
            <br />
        Enter form_details phrase to be split after(*warning):
            <textarea name="split"></textarea><hr>
            <br />
            </div>
            <p align="center">Channel: <textarea name="channel" placeholder="Enter channel" rows="1"></textarea><button name='send' value="change">Change Channel(title)</button><button name='send' value="change_id">Change Channel(id)</button><button name='send' value="return">Return to main</button><button name='send' value='reauth'>Reauth</button></p>
            <p align="center">Playlist: <select name='playlists'>
            <option value="choose">Choose:</option>
            """)
    else:
        all_forms = Markup(f"""<hr><form method="POST" id="form" name='form'>
                    <p align="center">Channel: <textarea name="channel" placeholder="Enter channel"></textarea><button name='send' value="change">Change Channel(title)</button><button name='send' value="change_id">Change Channel(id)</button><button name='send' value="return">Return to main</button><button name='send' value='reauth'>Reauth</button></p>
                    <p align="center">Playlist: <select name='playlists'>
                    <option value="choose">Choose:</option>
                    """)
    end_button = Markup(f"""</select><button name='send' value='playlists'>Route To</button></p>""")
    update_form_details = Markup(f"""<p align="center"><button name='send' value="update" style="height:35px;width:300px"><font size="2px">Update This Page</font></button></p>""")
    if not is_other_channel:
        end_button += update_form_details
    for page in range(0, len(playlists)):
        for z in range(0, len(playlists[page]['items'])):
            option_default = Markup(f"""<option value="playlist{z+(page*50)}">{z+(page*50)} {playlists[page]['items'][z]['snippet']['title']}</option>""")
            all_forms += "\n" + option_default
    all_forms += "\n" + end_button
    end_form = Markup(f"""Download:
        <input type="text" id="index" name="index" placeholder="Enter public index:">
        <button name='send' value="download">Download video</button></br>
        {fixed_channel_page_num}
        <button name='send' value="nextPage">Next Page</button>
        <button name='send' value="prevPage">Previous Page</button>
    </form>
    """)
    update_second = Markup(f"""</br><p align="center"><button name='send' value="update" style="height:100px;width:200px">Update This Page</button></br></p>""")
    if not is_other_channel:
        end_form = update_second + end_form
    for i in range(0, len(uploads_list["items"])):
        old_desc = uploads_list["items"][i]["snippet"]["description"]
        old_title = uploads_list["items"][i]["snippet"]["title"]
        vid_id = uploads_list["items"][i]["snippet"]["resourceId"]["videoId"]
        privacy = uploads_list["items"][i]["status"]["privacyStatus"]
        up_date = uploads_list["items"][i]["snippet"]["publishedAt"]
    # multiplying the number of form_styles, so no javascript. Remove iframe element if you don't want embed videos
        form_style = Markup(f"""
        Status: {privacy}</br>
        Date: {up_date}</br>
<span class="youtube-player" data-id="{vid_id}" data-related="0" data-control="0" data-info="1" data-fullscreen="0" style="width:20%;display: block; position: absolute;cursor: pointer;max-height:56px;height:100%; overflow:hidden;padding-bottom:8%;">
      <img src="//i.ytimg.com/vi/{vid_id}/hqdefault.jpg" style="bottom: -100%; display: block; left: 0; margin: auto; max-width: 100%; width: 100%;height:auto; position: absolute; right: 0; top: -100%;">
      <span style="height: 72px; width: 72px; left: 50%; top: 50%; margin-left: -36px; margin-top: -36px; position: absolute; background: url('https://i.imgur.com/TxzC70f.png') no-repeat;">
      </span> </span>
      <div style="margin-left: 325px;">
<font size="20pt">{i+(fixed_channel_page_num * 50)}</font>
Enter title:
        <textarea name="text{i}" id="title" rows="8" cols="35" style="font-size: 12pt; opacity: .8">{old_title}</textarea>
Enter description:
        <textarea name="text{i}" rows="10" cols="50" style="opacity: .8">{old_desc}</textarea>
        <button class="button" name='send' value="vdownload{i}">video</button>
        <button class="button" name='send' value="cdownload{i}">mp3</button></div>
<br />""")
        all_forms += "\n" + form_style
    all_forms += "\n" + end_form
    return render_template('hello.html', all_forms=all_forms, username=username)


@app.route('/', methods=['POST', 'GET'])
def index():
    client = get_client()
    channel_page_num = flask.session['channel_page_num']
    is_other_channel = flask.session['is_other_channel']
    channel_id = flask.session['channel_id']
    if is_other_channel:
        uploads_list = get_uploads(client, channel_page_num,
                                   id=channel_id,
                                   part='contentDetails, status',
                                   maxResults=50)
    else:
        uploads_list = get_uploads(client, channel_page_num,
                               mine=True,
                               part='contentDetails, status',
                               maxResults=50)
    # searching through button presses on only form
    print('boy')
    print(flask.session['test'])
    if request.method == 'POST':
        if request.form['send'] == 'update':
            appendtop_desc = request.form.get('appendtop')
            appendbottom_desc = request.form.get('appendbottom')
            replace_desc = request.form.get('replace')
            split_desc = request.form.get('split')
            for vid_num in range(0, len(uploads_list['items'])):
                form_details = request.form.getlist(f'text{vid_num}')
                title = form_details[0]
                description = (appendtop_desc + form_details[1] + appendbottom_desc)
                description = description.replace(replace_desc, "")
                if split_desc != '':
                    if len(description.split(split_desc)) == 2:
                        description = description.split(split_desc)[1]
                    else:
                        description = ''
                vid_id = uploads_list["items"][vid_num]["snippet"]["resourceId"]["videoId"]
                cat_url = requests.get(f"https://www.googleapis.com/youtube/v3/videos?part=snippet&id={vid_id}&key={keyfile.api_key}")
                cat = cat_url.json()
                # Category id is not listed for every vid number 
                # Default is 24 which should be 'Entertainment' in the US
                if cat["items"]:
                    cat_id = cat["items"][0]["snippet"]["categoryId"]
                else:
                    cat_id = '24'
                print(cat_id)
                videos_update(client,
                              {'id': vid_id,
                               'snippet.categoryId': cat_id,
                               'snippet.defaultLanguage': '',
                               'snippet.description': description,
                               'snippet.tags[]': '',
                               'snippet.title': title,
                               'status.privacyStatus': ''},
                              part='snippet,status'
                             )
            time.sleep(2)
            return flask.redirect(flask.url_for('my_form'))
        elif request.form['send'] == 'playlists':
            if request.form.get('playlists') != 'choose':
                playlist_num = int(request.form.get('playlists').split('playlist')[1])
                flask.session['playlist_num'] = playlist_num
                return flask.redirect(flask.url_for('my_playlist'))
        # Currently resetting session variable on major changes, remove if you want to keep pages.
        elif request.form['send'] == 'reauth':
            init_app()
            return flask.redirect('authorize')
        elif request.form['send'] == 'change':
            if request.form.get('channel') != '':
                try:
                    channel_name = request.form.get('channel')
                    channel = client.channels().list(
                                            part="contentDetails",
                                            forUsername=channel_name,
                                            ).execute()
                    flask.session['channel_id'] = channel['items'][0]["id"]
                    flask.session['channel_page_num'] = 0
                    flask.session['playlist_page_num'] = 0
                    flask.session['is_other_channel'] = True
                    return flask.redirect(flask.url_for('my_form'))
                except:
                    return '', 204
            else:
                return '', 204
        elif request.form['send'] == 'change_id':
            if request.form.get('channel') != '' and request.form.get('channel')[:2] == 'UC':
                try:
                    channel_id = request.form.get('channel')
                    channel = client.channels().list(
                        part="contentDetails",
                        id=channel_id,
                    ).execute()
                    flask.session['channel_id'] = channel['items'][0]["id"]
                    flask.session['channel_page_num'] = 0
                    flask.session['playlist_page_num'] = 0
                    flask.session['is_other_channel'] = True
                    return flask.redirect(flask.url_for('my_form'))
                except:
                    return '', 204
            else:
                return '', 204
        elif request.form['send'] == 'prevPage' and flask.session['channel_page_num'] != 0:
            flask.session['channel_page_num'] -= 1
            return flask.redirect(flask.url_for('my_form'))
        elif request.form['send'] == 'nextPage':
            flask.session['channel_page_num'] += 1
            return flask.redirect(flask.url_for('my_form'))
        elif request.form['send'] == 'return':
            flask.session['channel_page_num'] = 0
            flask.session['playlist_page_num'] = 0
            flask.session['is_other_channel'] = False
            return flask.redirect(flask.url_for('my_form'))
        elif 'download' in request.form['send']:
            if 'vdownload' in request.form['send']:
                res = AsyncResult(flask.session['id'])
                res.revoke()
                index_num = int(request.form['send'].split('vdownload')[1])
                result = videos_download.delay(index_num, False, uploads_list)
                flask.session['id'] = result.id
                #try checking result.id, then revoke task and rerun
            elif 'cdownload' in request.form['send']:
                res = AsyncResult(flask.session['id'])
                res.revoke()
                index_num = int(request.form['send'].split('cdownload')[1])
                print('starting')
                # experiment with trying to get celery tasks to work the first time through, debug
                result = videos_download.delay(index_num, True, uploads_list)
                flask.session['id'] = result.id
                print(result.id)
            elif len(request.form['send']) == 8:
                index_num = int(request.form.get('index'))
                videos_download(index_num, False, uploads_list)
    return '', 204


@app.route('/playlist/')
def my_playlist():
    client = get_client()
    channel_id = flask.session['channel_id']
    is_other_channel = flask.session['is_other_channel']
    first_playlist_page_num = flask.session['playlist_page_num']
    if is_other_channel:
        playlists = get_playlists(client,
                                  id=channel_id,
                                  part='contentDetails',
                                  maxResults=50
                                  )
    else:
        playlists = get_playlists(client,
                                  mine=True,
                                  part='contentDetails',
                                  maxResults=50
                                  )
    playlist_num = flask.session['playlist_num']
    key = int(playlist_num / 50)
    small_playlist_num = playlist_num % 50
    print(playlist_num)
    print(key)
    playlist_title = playlists[key]['items'][int(small_playlist_num)]['snippet']['title']
    playlist_id = playlists[key]['items'][int(small_playlist_num)]["id"]
    videos = get_playlist_uploads(client,
                                  first_playlist_page_num,
                                  playlist_id
                                  )
    fixed_playlist_page_num = flask.session['playlist_page_num']
    playlist_form = Markup(f"""<hr><form method='POST' id='form' name='form'>
    <p align="center">Playlist: <select name='playlists'>
        <option value="choose">Choose:</option>""")
    end_button = Markup(f"""</select><button name='send' value='playlists'>Route To</button></br><button name='send' value="uploads">Route to uploads</button></p>""")
    for page in range(0, len(playlists)):
        for z in range(0, len(playlists[page]['items'])):
            option_default = Markup(f"""<option value="playlist{z+(page*50)}">{z+(page*50)} {playlists[page]['items'][z]['snippet']['title']}</option>""")
            playlist_form += "\n" + option_default
    playlist_form += "\n" + end_button
    for i in range(0, len(videos["items"])):
        vid_id = videos["items"][i]["snippet"]["resourceId"]["videoId"]
        privacy = videos["items"][i]["status"]["privacyStatus"]
        old_desc = videos["items"][i]["snippet"]["description"]
        old_title = videos["items"][i]["snippet"]["title"]
        up_date = videos["items"][i]["snippet"]["publishedAt"]
        video_form = Markup(f"""
        Status: {privacy}</br>
        Date: {up_date}</br>
<span class="youtube-player" data-id="{vid_id}" data-related="0" data-control="0" data-info="1" data-fullscreen="0" style="width:20%;display: block; position: absolute;cursor: pointer;max-height:56px;height:100%; overflow:hidden;padding-bottom:8%;">
      <img src="//i.ytimg.com/vi/{vid_id}/hqdefault.jpg" style="bottom: -100%; display: block; left: 0; margin: auto; max-width: 100%; width: 100%;height:auto; position: absolute; right: 0; top: -100%;">
      <span style="height: 72px; width: 72px; left: 50%; top: 50%; margin-left: -36px; margin-top: -36px; position: absolute; background: url('https://i.imgur.com/TxzC70f.png') no-repeat;">
      </span> </span>
      <div style="margin-left: 325px;">
<font size="20pt">{i+(fixed_playlist_page_num * 50)}</font>
Enter title:
        <textarea name="text{i}" id="title" rows="8" cols="35" style="font-size: 12pt; opacity: .8">{old_title}</textarea>
Enter description:
        <textarea name="text{i}" rows="10" cols="50" style="opacity: .8">{old_desc}</textarea>
        <button class="button" name='send' value="vdownload{i}">video</button>
        <button class="button" name='send' value="cdownload{i}">mp3</button></div>
<br />""")
        playlist_form += '\n' + video_form
    playlist_form += '\n' + Markup(""" <button name='send' value="nextPage">Next Page</button>
        <button name='send' value="prevPage">Previous Page</button></form>""")
    return render_template('playlist.html', playlist_title=playlist_title, playlist_num=playlist_num, playlist_form=playlist_form)


@app.route('/playlist/', methods=["POST", "GET"])
def index_playlist():
    client = get_client()
    is_other_channel = flask.session['is_other_channel']
    channel_id = flask.session['channel_id']
    playlist_page_num = flask.session['playlist_page_num']
    if is_other_channel:
        playlists = get_playlists(client,
                                  id=channel_id,
                                  part='contentDetails',
                                  maxResults=50
                                  )
    else:
        playlists = get_playlists(client,
                              mine=True,
                              part='contentDetails',
                              maxResults=50
                              )
    playlist_num = flask.session['playlist_num']
    key = int(playlist_num / 50)
    small_playlist_num = playlist_num % 50
    playlists = playlists[key]
    playlist_id = playlists['items'][int(small_playlist_num)]["id"]
    videos = get_playlist_uploads(client, playlist_page_num, playlist_id)
    if request.method == 'POST':
        if request.form['send'] == 'uploads':
            return flask.redirect(flask.url_for('my_form'))
        if request.form['send'] == 'playlists':
            if request.form.get('playlists') != 'choose':
                playlist_num = int(request.form.get('playlists').split('playlist')[1])
                flask.session['playlist_num'] = playlist_num
                return flask.redirect(flask.url_for('my_playlist'))
        elif request.form['send'] == 'prevPage' and flask.session['playlist_page_num'] != 0:
            flask.session['playlist_page_num'] -= 1
            return flask.redirect(flask.url_for('my_playlist'))
        elif request.form['send'] == 'nextPage':
            flask.session['playlist_page_num'] += 1
            return flask.redirect(flask.url_for('my_playlist'))
        elif 'download' in request.form['send']:
            if 'vdownload' in request.form['send']:
                print('vdownload')
                index_num = int(request.form['send'].split('vdownload')[1])
                res = AsyncResult(flask.session['id'])
                res.revoke()
                result = videos_download.delay(index_num, False, videos)
                flask.session['id'] = result.id
            elif 'cdownload' in request.form['send']:
                # check if flask.session.get() by itself works or if you need 'is not None'
                # also implement code from vdownload here and change button to convert mp3, then add button download mp$
                # need to daemonize celery worker because after closing ubuntu terminal, the worker shuts down
                # see if this if statement is effective or if flask.session.pop('id') is truly deleting it
                res = AsyncResult(flask.session['id'])
                res.revoke()
                index_num = int(request.form['send'].split('cdownload')[1])
                print('starting')
                # experiment with trying to get celery tasks to work the first time through, debug
                result = videos_download.delay(index_num, True, videos)
                flask.session['id'] = result.id
            elif len(request.form['send']) == 8:
                index_num = int(request.form.get('index'))
                return videos_download(index_num, False, videos)
    return '', 204

def get_client():
    if 'credentials' not in flask.session:
        return flask.redirect('authorize')
    credentials = google.oauth2.credentials.Credentials(
        **flask.session['credentials'])
    client = googleapiclient.discovery.build(
        API_SERVICE_NAME, API_VERSION, credentials=credentials)
    return client

def get_playlist_uploads(client, page_num, playlist_id):
    temp_request = client.playlistItems().list(
        part="contentDetails,snippet,status",
        playlistId=playlist_id,
        maxResults=50
    )
    page_token = ''
    tokens = ['']
    playlist_items_response = []
    i = 0
    # This is the pagination loop for playlists, uses the prevPageToken of the playlist after the desired one
    # First playlist not used because the first playlist does not list nextPageToken, and currentPageToken doesn't exist
    while i < page_num and temp_request:
        playlist_items_response.append(temp_request.execute())
        if 0 <= i:
            current_result = playlist_items_response[i]
            try:
                token = current_result["nextPageToken"]
            except:
                break
            tokens.append(token)
        temp_request = client.playlistItems().list_next(
            temp_request, playlist_items_response[i])
        i += 1
    if flask.session.get('playlist_page_num') is None:
        return flask.redirect(flask.url_for('my_form'))
    if tokens:
        try:
            is_token = tokens[page_num]
        except:
            is_token = 'error'
        if is_token != 'error':
            page_token = tokens[page_num]
        else:
            page_token = tokens[page_num - 1]
            flask.session['playlist_page_num'] -= 1
    elif flask.session['playlist_page_num'] > 0:
        flask.session['playlist_page_num'] -= 1
    # Use past token that was placed in tokens list
    playlistitems_list_request = client.playlistItems().list(
        playlistId=playlist_id,
        part="snippet,status",
        maxResults="50",
        pageToken=page_token
    ).execute()
    return playlistitems_list_request


def get_playlists(client, **kwargs):
    channels = client.channels().list(
            **kwargs
    ).execute()
    channel_id = channels['items'][0]['id']
    temp_playlists = client.playlists().list(
        part="snippet, contentDetails",
        channelId=channel_id,
        maxResults=50
        )
    playlist_items_response = []
    i = 0
    # This is the pagination loop for playlists, uses the prevPageToken of the playlist after the desired one
    # First playlist not used because the first playlist does not list nextPageToken, and currentPageToken doesn't exist
    while temp_playlists:
        playlist_items_response.append(temp_playlists.execute())
        temp_playlists = client.playlistItems().list_next(
            temp_playlists, playlist_items_response[i])
        i += 1
    # Use past token that was placed in tokens list
    return playlist_items_response

# update with youtube-dl
@celery.task()
def videos_download(i, will_convert, playlist):
    video = playlist['items'][i]
    yt_url = YouTube("https://www.youtube.com/watch?v=" + video["snippet"]["resourceId"]["videoId"])
    yt_url.streams.filter(file_extension='mp4').first().download('./static/input')
    title_replace_list = ["'", ",", r"\"", "/", "|", ":", "?", ".", "*", "<", ">", "\""]
    filename = yt_url.title
    print('videos starting')
    for i in title_replace_list:
        filename = filename.replace(i, '')
    if will_convert:
        args = [f'{keyfile.loc_ffmpeg}', '-y', '-i', f'static/input/{filename}.mp4', '-ab', '160k', '-ac', '2', '-ar', '44100', '-vn', f'static/input/{filename}c.mp3']
        command = f'{keyfile.loc_ffmpeg} -y -i static/input/"{filename}.mp4" -ab 160k -ac 2 -ar 44100 -vn static/input/"{filename}c.mp3" > /dev/null 2>&1 < /dev/null'
        subprocess.call(command, shell=True)
        # ? need to save video in database seehttps://stackoverflow.com/questions/28626523/transcode-video-using-celery-and-ffmpeg-in-django
        # use envoy instead of subprocess?
        sys.stdout.write('hello')
        send_path = f'static/input/{filename}c.mp3'
        return send_path
    else:
        sys.stdout.write('bhello')
        print('to there')
        send_path = f'static/input/{filename}.mp4'
        return send_path

def videos_update(client, properties, **kwargs):
    # See full sample for function
    resource = build_resource(properties)

    # See full sample for function
    kwargs = remove_empty_kwargs(**kwargs)

    client.videos().update(
        body=resource,
        **kwargs
    ).execute()


# for loop for channel is not needed, but allows some expansion
def get_uploads(client, z, **kwargs):
    channels = client.channels().list(
            **kwargs
    ).execute()
    for channel in channels["items"]:
        uploads_list_id = channel["contentDetails"]["relatedPlaylists"]["uploads"]
        temp_request = client.playlistItems().list(
            playlistId=uploads_list_id,
            part="snippet,status",
            maxResults=50
        )
        page_token = ''
        tokens = ['']
        playlist_items_response = []
        i = 0
        while i < z and temp_request:
            playlist_items_response.append(temp_request.execute())
            if 0 <= i:
                current_result = playlist_items_response[i]
                try:
                    token = current_result["nextPageToken"]
                except:
                    break
                tokens.append(token)
            temp_request = client.playlistItems().list_next(
                temp_request, playlist_items_response[i])
            i += 1              #try to jsonify and get token, or combine and return combination of playlistresults
        if flask.session.get('channel_page_num') is None:
            return flask.redirect(flask.url_for('my_form'))
        if tokens:
            try:
                is_token = tokens[z]
            except:
                is_token = 'error'
            if is_token != 'error':
                page_token = tokens[z]
            else:
                page_token = tokens[z-1]
                flask.session['channel_page_num'] -= 1
        elif flask.session['channel_page_num'] > 0:
            flask.session['channel_page_num'] -= 1
        playlistitems_list_request = client.playlistItems().list(
                playlistId=uploads_list_id,
                part="snippet,status",
                maxResults="50",
                pageToken=page_token
            ).execute()
    return playlistitems_list_request


# Build a resource based on a list of properties given as key-value pairs.
# Leave properties with empty values out of the inserted resource.
def build_resource(properties):
    resource = {}
    for p in properties:
        # Given a key like "snippet.title", split into "snippet" and "title", where
        # "snippet" will be an object and "title" will be a property in that object.
        prop_array = p.split('.')
        ref = resource
        for pa in range(0, len(prop_array)):
            is_array = False
            key = prop_array[pa]

            # For properties that have array values, convert a name like
            # "snippet.tags[]" to snippet.tags, and set a flag to handle
            # the value as an array.
            if key[-2:] == '[]':
                key = key[0:len(key) - 2:]
                is_array = True

            if pa == (len(prop_array) - 1):
                # Leave properties without values out of inserted resource.
                if properties[p]:
                    if is_array:
                        ref[key] = properties[p].split(',')
                    else:
                        ref[key] = properties[p]
            elif key not in ref:
                # For example, the property is "snippet.title", but the resource does
                # not yet have a "snippet" object. Create the snippet object here.
                # Setting "ref = ref[key]" means that in the next time through the
                # "for pa in range ..." loop, we will be setting a property in the
                # resource's "snippet" object.
                ref[key] = {}
                ref = ref[key]
            else:
                # For example, the property is "snippet.description", and the resource
                # already has a "snippet" object.
                ref = ref[key]
    return resource


# Remove keyword arguments that are not set
def remove_empty_kwargs(**kwargs):
    good_kwargs = {}
    if kwargs is not None:
        for key, value in kwargs.items():
            if value:
                good_kwargs[key] = value
    return good_kwargs


@app.route('/authorize')
def authorize():
    # Create a flow instance to manage the OAuth 2.0 Authorization Grant Flow
    # steps.
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES)
    flow.redirect_uri = flask.url_for('oauth2callback', _external=True)
    authorization_url, state = flow.authorization_url(
        # This parameter enables offline access which gives your application
        # both an access and refresh token.
        access_type='offline',
        # This parameter enables incremental auth.
        include_granted_scopes='true')

    # Store the state in the session so that the callback can verify that
    # the authorization server response.
    flask.session['state'] = state
    return flask.redirect(authorization_url)


@app.route('/oauth2callback')
def oauth2callback():
    # Specify the state when creating the flow in the callback so that it can
    # verify the authorization server response.
    state = flask.session['state']
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES, state=state)
    flow.redirect_uri = flask.url_for('oauth2callback', _external=True)

    # Use the authorization server's response to fetch the OAuth 2.0 tokens.
    authorization_response = flask.request.url
    flow.fetch_token(authorization_response=authorization_response)

    # Store the credentials in the session.
    # ACTION ITEM for developers:
    #     Store user's access and refresh tokens in your data store if
    #     incorporating this code into your real app.
    credentials = flow.credentials
    flask.session['credentials'] = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }
    return flask.redirect(flask.url_for('my_form'))
