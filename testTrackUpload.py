#!/usr/bin/env python
# -*- coding: utf-8 -*-

from httpx import DigestAuth, get, post

import config


def main()
    auth = DigestAuth(config.targetuser, config.targetpassword)
    print('create mediapackage')
    resp = get(config.targetserver + "/ingest/createMediaPackage", headers=config.header, auth=auth)
    resp.raise_for_status()
    mp = resp.text
    print(f'mediapackage: {mp}')

    print('uploading track.mp4')
    payload = {'flavor': 'presentation/source', 'mediaPackage': mp, 'tags': 'archive, foo', 'BODY': ('track.mp4', open('track.mp4', 'rb'))}
    resp = post(config.targetserver + "/ingest/addTrack", headers=config.header, auth=auth, files=payload)
    resp.raise_for_status()
    mp = resp.text
    print(f'mediapackage: {mp}')

if __name__ == '__main__':
    main()