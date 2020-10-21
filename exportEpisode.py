import json, sys, httpx, re, os, xml
from io import BytesIO

from xml.etree import ElementTree
from xml.dom import minidom

import pycurl
from httpx import DigestAuth

import config
import handleSeries

from subprocess import Popen, PIPE, STDOUT
import addTrack

searchrequest = config.engageserver + config.searchendpoint + sys.argv[1]

archiverequest = config.archiveserver + config.archiveendpoint + sys.argv[1]

sourceauth = DigestAuth(config.sourceuser, config.sourcepassword)
targetauth = DigestAuth(config.targetuser, config.targetpassword)

# The Files will be downloaded to the lokal Disk, if false Opencast will download from set url in the Mediapackage
downloadToDisk = True

archivePresentationTracks = True


# Opencast sends an Object if list cotains only one Item instead of list
def jsonMakeObjectToList(jsonobject):
    if (not isinstance(jsonobject, list)):
        tmpObject = jsonobject
        jsonobject = []
        jsonobject.append(tmpObject)
        return jsonobject
    else:
        return jsonobject


def getMediapackageDataFromSearch():
    searchresult = httpx.get(searchrequest, auth=sourceauth, headers=config.header)
    print(searchrequest)
    searchresult = ElementTree.fromstring(searchresult.text)
    return searchresult


def getMediapackageDataFromArchive():
    archiveResult = httpx.get(archiverequest, auth=sourceauth, headers=config.header)
    print(archiverequest)
    archiveResult = ElementTree.fromstring(archiveResult.text)
    return archiveResult


def getMediapackageData():

    # Get mediapackage from episode/archive service
    archiveresult = getMediapackageDataFromArchive()
    searchresult = getMediapackageDataFromSearch()

    mediaPackage = mergeMediapackageSearchandMediapackageArchive(archiveresult, searchresult)

    return mediaPackage


def mergeMediapackageSearchandMediapackageArchive(archiveMp, searchMp):

    mediapackagexml= archiveMp.find('{http://search.opencastproject.org}result/{http://mediapackage.opencastproject.org}mediapackage/{http://mediapackage.opencastproject.org}metadata')
    print(prettifyxml(mediapackagexml))

    insertpoint = archiveMp.find('{http://search.opencastproject.org}result/{http://mediapackage.opencastproject.org}mediapackage/{http://mediapackage.opencastproject.org}metadata')
    for catalogs in searchMp.findall('{http://search.opencastproject.org}result/{http://mediapackage.opencastproject.org}mediapackage/{http://mediapackage.opencastproject.org}metadata/{http://mediapackage.opencastproject.org}catalog'):
      insertpoint.append(catalogs)

    insertpoint = archiveMp.find('{http://search.opencastproject.org}result/{http://mediapackage.opencastproject.org}mediapackage/{http://mediapackage.opencastproject.org}media')
    for tracks in searchMp.findall('{http://search.opencastproject.org}result/{http://mediapackage.opencastproject.org}mediapackage/{http://mediapackage.opencastproject.org}media/{http://mediapackage.opencastproject.org}track'):
      insertpoint.append(tracks)

    insertpoint = archiveMp.find('{http://search.opencastproject.org}result/{http://mediapackage.opencastproject.org}mediapackage/{http://mediapackage.opencastproject.org}attachments')
    for attachments in searchMp.findall('{http://search.opencastproject.org}result/{http://mediapackage.opencastproject.org}mediapackage/{http://mediapackage.opencastproject.org}attachments/{http://mediapackage.opencastproject.org}attachment'):
     insertpoint.append(attachments)

    return archiveMp


def createMediapackeOnIngestNode(mediaPackageId):
        # create mediapackage with right ID
        create_mediapackage_resp = httpx.put(config.targetserver + "/ingest/createMediaPackageWithID/" + mediaPackageId,
                                                headers=config.header, auth=targetauth)
        return create_mediapackage_resp.text


#  parse Tags to String list seperated by ,
def parseTagsToString(tags):
    # fix json bug, one element=not list element
    if type(tags) is list:
        # tags=t.get("tags")
        stringTags = ','.join(str(x) for x in tags)
        return stringTags
    else:
        # tags= t.get("tags").get("tag")
        return str(tags)

def getSignedURL(fileID,mediapacakgeID,xmlchild):
    url=''
    getURL= config.adminui+'/admin-ng/event/'+ mediapacakgeID +'/asset/'+xmlchild+'/'+fileID+'.json'
    print(getURL)
    trackJson = httpx.get(getURL, headers=config.header,
                                      auth=sourceauth).json()
    url = trackJson['url']
    print(url)

    return url

def addCatalogsviaUrl(mediapackageSearch, ingest_mp):

    for catalog in mediapackageSearch.findall('{http://mediapackage.opencastproject.org}metadata/{http://mediapackage.opencastproject.org}catalog'):
        tags = []
        print("Catalog ID\n" + str(catalog.get('id')))
        for tag in catalog.findall('{http://mediapackage.opencastproject.org}tags/{http://mediapackage.opencastproject.org}tag'):
            tags.append(tag.text)
        tags = ",".join(tags)

        urlFromMp = catalog.find('{http://mediapackage.opencastproject.org}url').text
        filename = str(urlFromMp.split("/")[-1])

        payload = {'flavor': str(catalog.get("type")), 'mediaPackage': str(ingest_mp), 'tags': str(tags), 'url' : str(urlFromMp)}
        print("Payload Catalogs\n"+ str(payload))
        print(config.targetserver)
        ingest_track_resp = httpx.post(config.targetserver + "/ingest/addCatalog", headers=config.header,
                                          auth=targetauth, data=payload)
        if ingest_track_resp.status_code == httpx.codes.ok:
            ingest_mp = ingest_track_resp.text
        print(ingest_track_resp.text)
        payload = {'flavor': 'dublincore/episode', 'mediaPackage': str(ingest_track_resp), 'tags': str(tags), 'url': str(urlFromMp)}
        ingest_track_resp = httpx.post(config.targetserver + "/ingest/addCatalog", headers=config.header,
                                          auth=targetauth, data=payload)

        if ingest_track_resp.status_code == httpx.codes.ok:
            ingest_mp = ingest_track_resp.text
        print(ingest_track_resp.text)
    return ingest_mp


# download catalogs with curl and upload them to the target opencast
def donwloadCatalogsAndUpload(mediapackageSearch, ingest_mp):

    for catalog in mediapackageSearch.findall('{http://mediapackage.opencastproject.org}metadata/{http://mediapackage.opencastproject.org}catalog'):
        tags = []
        print(catalog.get('id'))
        print(catalog.get('url'))
        for tag in catalog.findall('{http://mediapackage.opencastproject.org}tags/{http://mediapackage.opencastproject.org}tag'):
            tags.append(tag.text)
        tags = ",".join(tags)

        urlFromMp = catalog.find('{http://mediapackage.opencastproject.org}url').text
        filename = str(urlFromMp.split("/")[-1])

        #DownloadFile
        command = "curl --digest -u " + config.sourceuser + ":" + config.sourcepassword + " -H 'X-Requested-Auth: Digest' '" + urlFromMp + "' -o " + filename
        print(command)
        os.system(command)
        files = {'file': open(filename, 'rb')}

        payload = {'flavor': str(catalog.get("type")), 'mediaPackage': str(ingest_mp), 'tags': str(tags)}
        print(payload)
        print(config.targetserver)
        ingest_track_resp = httpx.post(config.targetserver + "/ingest/addCatalog", headers=config.header,
                                          files=files, auth=targetauth, data=payload)
        if ingest_track_resp.status_code == httpx.codes.ok:
            ingest_mp = ingest_track_resp.text
        print(ingest_track_resp.text)
        # payload = {'flavor': 'dublincore/episode', 'mediaPackage': str(ingest_track_resp), 'tags': str(tags)}
        # ingest_track_resp = httpx.post(config.targetserver + "/ingest/addCatalog", headers=config.header,
        #                                   files=files, auth=targetauth, data=payload)
        #
        # if ingest_track_resp.status_code == httpx.codes.ok:
        #     ingest_mp = ingest_track_resp.text
        print(ingest_track_resp.text)
        os.remove(filename)
    return ingest_mp


# download attachments with curl and upload them to the target opencast
def downloadAttachmentsAndUpload(mediapackageSearch, ingest_mp):
     print("--Uploading Catalogs--")
     for attechment in mediapackageSearch.findall('{http://mediapackage.opencastproject.org}attachments/{http://mediapackage.opencastproject.org}attachment'):
        tags = []
        print(attechment.get('id'))
        for tag in attechment.findall('{http://mediapackage.opencastproject.org}tags/{http://mediapackage.opencastproject.org}tag'):
            tags.append(tag.text)
        tags = ",".join(tags)

        urlFromMp = attechment.find('{http://mediapackage.opencastproject.org}url').text
        filename = str(urlFromMp.split("/")[-1])

        #DownloadFile
        command = "curl --digest -u " + config.sourceuser + ":" + config.sourcepassword + " -H 'X-Requested-Auth: Digest' '" + urlFromMp + "' -o " + filename
        print(command)
        os.system(command)
        files = {'file': open(filename, 'rb')}


        payload = {'flavor': attechment.get("type"), 'mediaPackage': ingest_mp, 'tags': tags}
        ingest_track_resp = httpx.post(config.targetserver + "/ingest/addAttachment", headers=config.header,
                                          files=files, auth=targetauth, data=payload)
        if ingest_track_resp.status_code == httpx.codes.ok:
          ingest_mp = ingest_track_resp.text
        os.remove(filename)
     return ingest_mp



def addTracksviaURL(mediapackageSearch, ingest_mp):

    for track in mediapackageSearch.findall('{http://mediapackage.opencastproject.org}media/{http://mediapackage.opencastproject.org}track'):
        tags = []

        for tag in track.findall('{http://mediapackage.opencastproject.org}tags/{http://mediapackage.opencastproject.org}tag'):
            tags.append(tag.text)
        tags = ",".join(tags)

        urlFromMp = track.find('{http://mediapackage.opencastproject.org}url').text
        filename = str(urlFromMp.split("/")[-1])

        payload = {'flavor': track.get("type"), 'mediaPackage': ingest_mp, 'tags': tags, 'url': urlFromMp}
        ingest_track_resp = httpx.post(config.targetserver + "/ingest/addTrack", headers=config.header,
                                          auth=targetauth, data=payload)
        if ingest_track_resp.status_code == httpx.codes.ok:
            ingest_mp = ingest_track_resp.text
    return ingest_mp

def downloadTracksAndUpload(mediapackageSearch, ingest_mp):

    for track in mediapackageSearch.findall('{http://mediapackage.opencastproject.org}media/{http://mediapackage.opencastproject.org}track'):
        tags = []

        for tag in track.findall('{http://mediapackage.opencastproject.org}tags/{http://mediapackage.opencastproject.org}tag'):
            tags.append(tag.text)
        tags = ",".join(tags)

        urlFromMp = track.find('{http://mediapackage.opencastproject.org}url').text
        filename = str(urlFromMp.split("/")[-1])

        #DownloadFile
        command = "curl --digest -u " + config.sourceuser + ":" + config.sourcepassword + " -H 'X-Requested-Auth: Digest' '" + urlFromMp + "' -o " + filename
        print(command)
        os.system(command)
        # files = {'file': open(filename, 'rb')}
        #
        # data = {'flavor': track.get("type"), 'mediaPackage': ingest_mp, 'tags': tags}
        # files = {'BODY': (filename, open(filename, 'rb'))}
        # ingest_track_resp = httpx.post(config.targetserver + "/ingest/addTrack", headers={"X-Requested-Auth": "Digest"},
        #                                    auth=targetauth, data=data, files=files)
        # if ingest_track_resp.status_code == httpx.codes.ok:
        #     print("----   Ingested Tracks \n"+ ingest_track_resp.text)
        #     ingest_mp = ingest_track_resp.text

        ingest_mp = ingest_track(ingest_mp, track.get("type"), filename, tags)
        print("----   Ingested Tracks \n" + ingest_mp)
        os.remove(filename)
    return ingest_mp


def ingest_track(mp: str,
                 flavor: str,
                 track_url: str,
                 tags: str):
    url_path = '/ingest/addTrack'
    data = [
        ('mediaPackage', mp),
        ('flavor', flavor),
        ('tags', tags),
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
    return result.decode('utf-8')


def prettifyxml(elem):
    """Return a pretty-printed XML string for the Element.
    """
    rough_string = ElementTree.tostring(elem, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ")


def ingestMediapackage(mediapackage):
    #print(mediapackage)
    mediapackage = prettifyxml(ElementTree.fromstring(mediapackage))
    f = open('mediapackage.xml', 'w')
    f.write(mediapackage)
    f.close()
    payload = {'mediaPackage': mediapackage}
    ingest_track_resp = httpx.post(config.targetserver + "/ingest/ingest/" + config.targetworkflow,
                                      headers=config.header, auth=targetauth, data=payload)
    print(ingest_track_resp.text)
    print("Ingesting done")

def addSeriesIfexist(mediapackageSource):
    try:
      mediapackageSource.find('{http://mediapackage.opencastproject.org}series').text
      seriesId= mediapackageSource.find('{http://mediapackage.opencastproject.org}series').text
      handleSeries.handleSeries(seriesId)
    except:
      print("no series attached")

def main():
    #sys.setdefaultencoding('utf-8')
    ingest_mp = createMediapackeOnIngestNode(sys.argv[1])

    mediapackageSource = getMediapackageData()
    mediapackageSource= mediapackageSource.find('{http://search.opencastproject.org}result/{http://mediapackage.opencastproject.org}mediapackage')
    print(prettifyxml(mediapackageSource))
    addSeriesIfexist(mediapackageSource)
    text_file = open  ("sourcexml.xml", "w")
    n = text_file.write(prettifyxml(mediapackageSource))
    text_file.close()

    #print(prettifyxml(mediapackagexmltree))


    ingest_mp = donwloadCatalogsAndUpload(mediapackageSource, ingest_mp)
    ingest_mp = downloadAttachmentsAndUpload(mediapackageSource, ingest_mp)
    ingest_mp = downloadTracksAndUpload(mediapackageSource, ingest_mp)




    #print(prettifyxml(ElementTree.fromstring(ingest_mp)))
    ingestMediapackage(ingest_mp)




if __name__ == "__main__":
    main()
