import time
import json
from flask import Flask,request, Response,jsonify, make_response
from functools import wraps
import requests
from requests.auth import HTTPBasicAuth

app = Flask(__name__)
            
#Checks username and password
def check_auth(username, password):
    return username == 'petco' and password == 'petco123'
#Returns if authenticated or not
def authenticate():
    return Response(
    'Could not verify your access level for that URL.\n'
    'You have to login with proper credentials', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})
#creates the decorator the enables auth on endpoints
def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated



@app.route('/', methods = ['POST'])
def availability():
    request_details = request.get_json()
    SKU_Number = request_details['queryResult']['parameters']['any']
    SKU_Number = SKU_Number.replace(" ", "")
    req = request.get_json(silent=True, force=True)
    headers = {'Content-Type':'application/json'}
    url = 'http://DDCSPINGBTP01VL.petc.com:8080/inventory/availability'
    
    data = {
    "zipCode": 'true',
    "shipInfoRequired": False,
    "inventoryItemsRequest": [
        {
            "item": {
                "itemID": str(SKU_Number),
                "uom": "EACH"
            },
            "storeInfoRequired": True,
            "distributionGroupName": "SFS_DG"
        }
    ],
    "orgCode": "PETCOUS"
    }
    
    try:
        #trigger API to get availability for the SKU
        response = requests.post(url = url, data=json.dumps(data), headers=headers, auth=('273ada0c60a8e1fa', 'fa3d0038c8254c50'))
        Availability_response = response.json() 
        #check if the store is being searched for
        if request_details['queryResult']['parameters']['StoreNumber']:
            store_number = request_details['queryResult']['parameters']['StoreNumber']
            
            number_of_locations = len(Availability_response['response']['itemAvailabilityDetails'][0]['itemAvailabilityAtLocations'])
            location_array = Availability_response['response']['itemAvailabilityDetails'][0]['itemAvailabilityAtLocations']
            #loop here that cycles through right store number
            for i in range(0, number_of_locations):
                #If store number is found - return BOPUS availability to google assistant
                if store_number == location_array[i]['locationId']:
                    return make_response(jsonify({'fulfillmentText': 'Store '+store_number +' has '+ str(location_array[i]['bopusAtp']) +' Pickup Units'}))
              
            
            return make_response(jsonify({'fulfillmentText': 'No store has item ' + SKU_Number}))
        else:
            #in case the store was not available - and want enterprise ATP 
            ATP = str(Availability_response['response']['itemAvailabilityDetails'][0]['shipAtp'])
            return make_response(jsonify({'fulfillmentText': 'You have '+ATP +' Total Units'}))
    except Exception as e:
        return make_response(jsonify({'fulfillmentText': 'Error try again'}))

#endpoint to get all of the notifications in DynamoDB
@app.route('/getallnotificationrecords')
@requires_auth
def getallnotificationrecords():
    notifications = []
    Notifications_Search = notification_records.scan() 
    for notification in Notifications_Search["Items"]:
        notifications.append({
            "OrderID" : notification["OrderID"],
            "OrderCreationDate" : notification["OrderCreationDate"],
            "StoreID" : int(notification["StoreID"]),
            "NotificationCreationDate" : notification["NotificationCreationDate"],
            "ReadReceiptStatus" : int(notification["ReadReceiptStatus"])
            }
        )
    return jsonify({"Success" : True , "Payload" : notifications})

#New order submitted from OMS
@app.route('/addorder', methods=['POST'])
@requires_auth
def addorder():    
    #change request received through endpoint to JSON
    Payload = request.json
    #create the insert object into DB
    BOPUS_Order = {
                "ID" : uuid.uuid4().hex,
                "OrderID" : Payload["OrderID"],
                "OrderCreationDate" : Payload["OrderCreationDate"],
                "StoreID" : int(Payload["StoreID"]),
                "NotificationCreationDate" : time.strftime('%x %X'),
                "ReadReceiptStatus" : 0,
    }
    #inset object into Dynamodb
    if Payload["dev_flag"] == False:
        notification_records.put_item(Item = BOPUS_Order)
    response = store_information.scan( FilterExpression=Attr('StoreID').eq(Payload["StoreID"]) )
    #Find all devices attached to the specified store, and send notification - Try/except to skip if a notification error occurs
    if Payload["dev_flag"] == False:
        for Device in response['Items']:
            sendpushnotification(Device["DeviceToken"], Payload["OrderID"],Payload["StoreID"], False)
    return jsonify({"Success" : True})    

#Indicate that the store received the notification
@app.route('/readnotification', methods=['POST'])
@requires_auth
def readnotification():
    Payload = request.json
    StoreID = int(Payload["StoreID"])
    Notification_Search = notification_records.scan( FilterExpression=Attr('StoreID').eq(StoreID))    
    for notification in Notification_Search["Items"]:      
        notification_records.update_item(
            Key= {
                "ID" : notification["ID"]
            },
            UpdateExpression='SET ReadReceiptStatus = :val1',
        ExpressionAttributeValues={
            ':val1': 1
        })
    return jsonify({"Success" : True})

#register device token
@app.route('/registerdevice', methods=['POST'])
@requires_auth
def registerdevicetoken():
    #change request to JSON and grab the required variables
    Payload = request.json
    DeviceToken = Payload["DeviceToken"]
    StoreID = Payload["StoreID"]
    #check if the store exists in MongoDB
    Device_Search = store_information.scan( FilterExpression=Attr('DeviceToken').eq(DeviceToken))    
  
    if (Device_Search["Count"] == 0):
        store_information.put_item(Item = {"ID" : uuid.uuid4().hex, "DeviceToken" : DeviceToken, "StoreID" : StoreID})
    else:
        for Device in Device_Search["Items"]:
            store_information.update_item(
        Key={
            'ID': Device["ID"]
        },
        UpdateExpression='SET StoreID = :val1',
        ExpressionAttributeValues={
            ':val1': StoreID
        }
        )   
    return jsonify({"Success" : True})

@app.route('/getallregistereddevices', methods=['GET'])
@requires_auth
def getallregistereddevices():
    #change request to JSON and grab the required variables
    Registerd_Devices = []
    #find all devices
    Devices = store_information.scan()
    for device in Devices["Items"]:
        Registerd_Devices.append( {
            "StoreID" : int(device["StoreID"]),
            "DeviceToken" : device["DeviceToken"]
            }
        )
    return jsonify({"Success" : True , "Payload" : Registerd_Devices})

@app.route('/deletealldevices', methods=['DELETE'])
@requires_auth
def deletealldevices():
    #change request to JSON and grab the required variables
    response = store_information.scan()
    for device in response['Items']:
        store_information.delete_item(Key={"ID" : device["ID"]})     
    return jsonify({"Success" : True})

@app.route('/sendpushnotification', methods=['POST'])
@requires_auth
def pushnotification():
    Payload = request.json
    sendpushnotification(Payload["DeviceToken"], Payload["OrderID"],Payload["StoreID"], Payload["dev_flag"])
    return jsonify({"Sucess": True})

#Finds all of the registered devices for a store
@app.route('/CheckRegisteredDevices/<int:StoreID>', methods=['GET'])
@requires_auth
def CheckRegisteredDevices(StoreID):
    Registerd_Devices = []
    Devices = store_information.scan(FilterExpression=Attr('StoreID').eq(StoreID) )
    for device in Devices["Items"]:
        Registerd_Devices.append( {
            "StoreID" : int(device["StoreID"]),
            "DeviceToken" : device["DeviceToken"]
            }
        )
    return jsonify({"Success" : True , "Payload" : Registerd_Devices})

#Find alerts that have not been acknowledged in a store
@app.route('/CheckUnreadAlerts/<int:StoreID>', methods=['GET'])
@requires_auth
def CheckUnreadAlerts(StoreID):
    Unread_Alerts = []
    Alerts = notification_records.scan(FilterExpression=Attr('StoreID').eq(StoreID) & Attr('ReadReceiptStatus').eq(0))
    for Alert in Alerts["Items"]:
        Unread_Alerts.append( {
            "OrderID" : Alert["OrderID"],
            "ReadReceiptStatus" : int(Alert["ReadReceiptStatus"])
            }
        )
    print(Unread_Alerts)
    return jsonify({"Success" : True , "Payload" :  Unread_Alerts})


if __name__ == "__main__":

    #Running the flask app
    app.run(host="0.0.0.0",port = 8080) 