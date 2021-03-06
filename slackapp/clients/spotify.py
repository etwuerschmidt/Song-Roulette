
import sys
sys.path.append('..')
from slackapp import app
import base64
import datetime
import os
import requests
import spotipy
import spotipy.util as util


class SpotifyClient():
    """Class for handling all Spotify API requests"""

    refresh_url = 'https://accounts.spotify.com/api/token'

    def __init__(self, user_id=None, username=None, **kwargs):
        """Initializes an object with all necessary items to create a Spotify Client"""
        self.client = None
        self.client_id = kwargs.get(
            'SPOTIPY_CLIENT_ID', os.environ['SPOTIPY_CLIENT_ID'])
        self.client_secret = kwargs.get(
            'SPOTIPY_CLIENT_SECRET', os.environ['SPOTIPY_CLIENT_SECRET'])
        self.fields_filter = 'items(added_at,added_by,track(name,popularity,uri))'
        self.scope = "playlist-read-collaborative playlist-read-private playlist-modify-private playlist-modify-public"
        self.redirect_uri = kwargs.get('SPOTIPY_REDIRECT_URI', os.environ['SPOTIPY_REDIRECT_URI'])
        # all_songs_sr_analysis should be taken into account for Song Roulette: All, since songs for a particular month are added on the first day
        # of the following month
        self.all_songs_sr_analysis = False
        self.user_id = user_id
        self.username = username
        self.access_token = None
        self.refresh_token = os.environ['SPOTIFY_REFRESH_TOKEN']
        self.last_refresh = 0

    def connect(self, with_prompt=False):
        """Authentication for Spotify Client"""
        if with_prompt:
            token = util.prompt_for_user_token(self.username, self.scope, client_id=self.client_id,
                               client_secret=self.client_secret, redirect_uri=self.redirect_uri)
        else:
            self.refresh_access()

    def filter_tracks(self, playlist_items, field):
        """Return a list of playlist items with the given filter field"""
        return [track['track'][field] for track in playlist_items]

    def get_audio_features(self, songs):
        """Returns audio features given a list of songs. Audio features call does not support offsetting, so list slicing is required."""
        return self.max_out_with_slice(self.client.audio_features, songs)

    def get_month_tracks(self, playlist_name, month, year, fields=None):
        """Returns the filtered track information of a given playlist name for tracks added in a specific month"""
        if month not in list(range(1, 13)):
            print("Please provide month as an integer")
            exit()
        if fields is not None and "added_at" not in fields:
            print("Please include added_at filter in fields")
            exit()
        filtered_tracks = []
        tracks = self.get_playlist_tracks(playlist_name, fields=fields)
        for track in tracks:
            track_date = datetime.datetime.strptime(
                track['added_at'], '%Y-%m-%dT%H:%M:%SZ')
            if track_date.month - int(self.all_songs_sr_analysis) == month and track_date.year == year:
                filtered_tracks.append(track)
        return filtered_tracks

    def get_playlist_id(self, playlist_name):
        """Returns a playlist ID for a given playlist name"""
        pid = -1
        all_playlists = self.client.current_user_playlists()
        for playlist in all_playlists['items']:
            if playlist['name'] == playlist_name:
                pid = playlist['id']
        if pid == -1:
            app.logger.error("Playlist with name '%s' not found!" % playlist_name)
            raise ValueError("Playlist with name '%s' not found!" % playlist_name)
        return pid

    def get_playlist_tracks(self, playlist_name, fields=None):
        """Returns the filtered track information of a given playlist name"""
        app.logger.info(f"Fetching tracks for playlist {playlist_name}")
        fields = self.fields_filter if fields is None else fields
        pid = self.get_playlist_id(playlist_name)
        tracks = self.max_out_with_offset(
            self.client.user_playlist_tracks, user=self.user_id, playlist_id=pid, fields=fields)
        return sorted(tracks, key=lambda track: track['added_at']) if 'added_at' in fields else tracks

    def get_playlist_url(self, playlist_name):
        """Returns a playlist URL for a given playlist name"""
        playlist = self.client.user_playlist(
            self.user_id, self.get_playlist_id(playlist_name))
        return playlist['external_urls']['spotify']

    def max_out_with_slice(self, method_name, tracks, **kwargs):
        """Makes multiple requests when information is needed for >100 tracks for API endpoints that don't support offset"""
        counter = 0
        track_count = 100
        all_items = []
        while track_count == 100:
            end_slice = 100*(counter+1) if len(tracks) > 100 * \
                (counter + 1) else len(tracks)
            items = method_name(tracks=tracks[100*counter:end_slice], **kwargs)
            all_items += items
            track_count = end_slice - 100*counter
            counter += 1
        return all_items

    def max_out_with_offset(self, method_name, **kwargs):
        """Makes multiple requests when information is needed for >100 tracks for API endpoints that support offset"""
        counter = 0
        track_count = 100
        all_items = []
        while track_count == 100:
            items = method_name(**kwargs, offset=100*counter)
            all_items += items['items']
            track_count = len(items['items'])
            counter += 1
        return all_items

    def move_tracks(self, from_playlist, to_playlist):
        """Move all tracks from one playlist to another"""
        app.logger.info(f"Moving tracks from {from_playlist} to {to_playlist}")
        from_id = self.get_playlist_id(from_playlist)
        to_id = self.get_playlist_id(to_playlist)
        tracks = self.get_playlist_tracks(from_playlist)
        tracks_to_move = [track['track']['uri'] for track in tracks]
        self.max_out_with_slice(self.client.user_playlist_add_tracks,
                                tracks_to_move, user=self.user_id, playlist_id=to_id)
        self.max_out_with_slice(self.client.user_playlist_remove_all_occurrences_of_tracks,
                                tracks_to_move, user=self.user_id, playlist_id=from_id)

    def refresh_access(self):
        if self.last_refresh == 0 or datetime.datetime.utcnow() > self.last_refresh + datetime.timedelta(minutes=55):
            app.logger.info(
               'Invalid or nonexistant Spotify token, requesting new token now')
            header_auth_info = self.client_id + ":" + self.client_secret
            b64_header_auth_info = base64.urlsafe_b64encode(
                header_auth_info.encode()).decode()
            headers = {'Authorization': f"Basic {b64_header_auth_info}",
                'Content-Type': 'application/x-www-form-urlencoded'}
            payload = {'grant_type': 'refresh_token',
                'refresh_token': self.refresh_token}
            refresh_request = requests.post(
                self.refresh_url, headers=headers, data=payload)
            self.access_token = refresh_request.json()['access_token']
            self.client = spotipy.Spotify(auth=self.access_token)
            self.last_refresh = datetime.datetime.utcnow()
        else:
           app.logger.info('Token is still valid')

    def rename_playlist(self, old_playlist_name, new_playlist_name):
        """Renames a playlist given old and new playlists"""
        app.logger.info(f"Renaming {old_playlist_name} to {new_playlist_name}")
        self.client.user_playlist_change_details(
            self.user_id, self.get_playlist_id(old_playlist_name), new_playlist_name)

    def set_fields(self, fields):
        """Set the fields parameter used when making REST requests"""
        self.fields_filter = fields


if __name__ == "__main__":
    my_client = SpotifyClient()
    my_client.connect()
    my_client.fields_filter = None
    pl_tracks = my_client.get_playlist_tracks(
        "Tabletops", fields='items(track(name,popularity,uri))')
    track_uris = my_client.filter_tracks(pl_tracks, 'uri')
    print(len(my_client.get_audio_features(track_uris)))
    exit()
