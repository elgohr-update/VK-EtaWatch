#!/usr/bin/env python3

import json

# to run a permanent job
import schedule
import time

# to load the current variables from eta
import requests
import xml.etree.ElementTree as ET
import os

# to store the measurements
import datetime
from influxdb import InfluxDBClient

etaUrl = os.environ.get("ETA_URL", "http://eta:8080")

influxHost = os.environ.get("INFLUX_HOST", "influxdb")


def to_camel(text):
    """
    to convert the initial variable strings
    """
    return '>>'.join(''.join(y.capitalize() or ' ' for y in x.split(' ')) or '>>' for x in text.split('>>'))


def get_all_uris(data: ET.Element):
    """
    Create a list of uris which have some recordable data
    """
    alluris = {}

    for child1 in data:
        for child2 in child1:
            if child2.attrib['uri'].count('/') > 2:
                newname = child1.attrib['name'] + ">>"+child2.attrib['name']
                uri = child2.attrib['uri']
                alluris[to_camel(newname)] = uri
            for child3 in child2:
                newname = child1.attrib['name']+">>" + \
                    child2.attrib['name']+">>"+child3.attrib['name']
                uri = child3.attrib['uri']
                alluris[to_camel(newname)] = uri
                for child4 in child3:
                    newname = child1.attrib['name']+">>"+child2.attrib['name'] + \
                        ">>" + child3.attrib['name'] + \
                        ">>"+child4.attrib['name']
                    uri = child4.attrib['uri']
                    alluris[to_camel(newname)] = uri


    #print("# all uris:")
    #print(json.dumps(alluris, indent=2))
    return alluris


def get_data(uri):
    """
    Extract the values of an uri
    """
    output = {}
    res = requests.get(etaUrl+"/user/var"+uri)
    if (res.status_code != 200):
        print("ERROR: no connection to {}{}".format(etaUrl, uri))
    else:
        # go on with data parsing:
        data = ET.fromstring(res.content)

        # or data[0].attrib["strValue"] == "xxx":
        if data[0].attrib["strValue"] == "":
            return None

        output['val'] = (float(
            data[0].text)-float(data[0].attrib['advTextOffset']))/float(data[0].attrib['scaleFactor'])
        try:
            if data[0].attrib['unit'] != "":
                output['text'] = (str(output['val'])+" " +
                                  data[0].attrib['unit'])
            else:
                output['text'] = str(output['val'])
            output['type'] = "num"
        except:
            output['text'] = (data[0].attrib['strValue'] +
                              data[0].attrib['unit'])
            output['type'] = "cat"

        output['unit'] = data[0].attrib['unit']
        output['scaleFactor'] = float(data[0].attrib['scaleFactor'])


    return output


def check_influx():
    """
    create the database if needed
    """
    client = InfluxDBClient(host=influxHost, port=8086)
    if len([v for v in client.get_list_database() if v["name"] == "eta"]) == 0:
        print("create eta db")
        client.create_database('eta')
    client.close()


def job():
    """
    a single update job
    """

    now = datetime.datetime.now().strftime("%m/%d/%Y, %H:%M:%S")
    
    try:
        check_influx()
    except:
        print(f"[{now}] ERROR: Influx DB not available!")
        return -5

    # query eta for all uris
    try:
        res = requests.get(etaUrl+"/user/menu")
    except:
        print(f"[{now}] ERROR: no connection to {etaUrl}")
        return -10        
    

    if (res.status_code != 200):
        print(f"[{now}] ERROR: no connection to {etaUrl}")
        return -10
    
    try:
        data = ET.fromstring(res.content)
        uris = get_all_uris(data[0])

        # connect to influxdb
        client = InfluxDBClient(host=influxHost, port=8086)
        client.switch_database('eta')

        # collect data
        timestamp = str(datetime.datetime.utcnow())
        alldata = {k: v for k, v in {name: get_data(uri) for name, uri in uris.items()}.items() if v}

        # send an entry
        client.write_points([{
            "measurement": "eta",
            "time": timestamp,
            "fields": {k: v['val'] if v['type'] == 'num' else v['text'] for k, v in alldata.items()}
        }])
        print(f"[{now}] send data")

        client.close()
    except:
        print("ERROR: Not able to add new values.")
        return -15


def main():
    
    schedule.every(1).minutes.do(job)

    while 1:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()
