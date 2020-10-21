#!/usr/bin/env python
# -*- coding: utf-8 -*-

from io import BytesIO

import pycurl as pycurl
from httpx import DigestAuth, get

import config


def main():
    auth = DigestAuth(config.targetuser, config.targetpassword)
    print('create mediapackage')
    resp = get(config.targetserver + "/ingest/createMediaPackage", headers=config.header, auth=auth)
    resp.raise_for_status()
    mp = resp.text
    print(f'mediapackage: {mp}')

    # print('uploading track.mp4')
    # data = {'flavor': 'presentation/source', 'mediaPackage': mp, 'tags': 'archive, foo'}
    # files = {'BODY': ('track.mp4', open('track.mp4', 'rb'), 'video/mp4')}
    # resp = post(config.targetserver + "/ingest/addTrack", headers=config.header, auth=auth, data=data, files=files)
    # resp.raise_for_status()
    # mp = resp.text

    print('uploading track.mp4 with pycurl')
    mp = ingest_track(mp, 'presenter/source', 'track.mp4')
    print(f'mediapackage: {mp}')


def ingest_track(mp: str,
                 flavor: str,
                 track_url: str):
    url_path = '/ingest/addTrack'
    data = [
        ('mediaPackage', mp),
        ('flavor', flavor),
        ('BODY', (pycurl.FORM_FILE, track_url))
    ]
    headers = dict()
    c = pycurl.Curl()
    c.setopt(pycurl.URL, (config.targetserver + url_path).encode('ascii', 'ignore'))
    c.setopt(pycurl.HTTPAUTH, pycurl.HTTPAUTH_DIGEST)
    c.setopt(pycurl.USERPWD, f'{config.targetuser}:{config.targetpassword}')
    headers = config.header
    c.setopt(pycurl.HTTPHEADER, ['{}: {}'.format(k, v) for (k, v) in headers.items()])
    c.setopt(pycurl.HTTPPOST, data)
    buf = BytesIO()
    c.setopt(pycurl.WRITEFUNCTION, buf.write)
    c.setopt(pycurl.FOLLOWLOCATION, True)
    print("start ingesting track {} as {}".format(track_url, flavor))
    c.perform()
    status = c.getinfo(pycurl.HTTP_CODE)
    c.close()
    if int(status / 100) != 2:
        raise Exception('Request to {} failed, HTTP error code {}'
                        .format(url_path, status))
    result = buf.getvalue()
    buf.close()
    return result

if __name__ == '__main__':
    main()