#!/usr/bin/env python
# -*- coding: utf-8 -*-

from httpx import DigestAuth, get, post

import config


def main():
    auth = DigestAuth(config.targetuser, config.targetpassword)
    print('create mediapackage')
    resp = get(config.targetserver + "/ingest/createMediaPackage", headers=config.header, auth=auth)
    resp.raise_for_status()
    mp = resp.text
    print(f'mediapackage: {mp}')

    print('uploading track.mp4')
    data = {'flavor': 'presentation/source', 'mediaPackage': mp, 'tags': 'archive, foo'}
    files = {'BODY': ('track.mp4', open('track.mp4', 'rb'), 'video/mp4')}
    resp = post(config.targetserver + "/ingest/addTrack", headers=config.header, auth=auth, data=data, files=files)
    resp.raise_for_status()
    mp = resp.text
    print(f'mediapackage: {mp}')

if __name__ == '__main__':
    main()