from influxdb import InfluxDBClient
import sys, os
from datetime import datetime
from time import strftime
import numpy as np
import statsmodels
from configparser import ConfigParser
import smtplib
from email.mime.text import MIMEText	
from email.mime.multipart import MIMEMultipart

# Loads settings
parser = ConfigParser()
parser.read('EmailWarning.config')

try:
    influx_url = parser.get('influx', 'url')
    influx_port = parser.get('influx', 'port')
    influx_user = parser.get('influx', 'username')
    influx_pwd = parser.get('influx', 'password')
    influx_db = parser.get('influx', 'database')
    client = InfluxDBClient(influx_url, influx_port, influx_user, influx_pwd, influx_db)
except ConnectionError as e:
    print ("Error: Could not connect to server.")

influx_tag = parser.get('influx', 'tag')
influx_number = parser.get('influx', 'number')
influx_number = int(influx_number)
curr = client.query("select * from temperature where channel_name = '{0}' order by DESC limit {1} offset 0".format(influx_tag, influx_number)).get_points('temperature')
curr = [x['value'] for x in curr]

curr = np.array(curr)
failure_indices = []

# Filters outliers using MAD to prevent false positives during failure detection
def filter_outliers(data, sigma_num): # Sigma_num is the number of deviations above or below the median
    k = 1.4826 # Constant scaling factor; for normally distributed data, k is approximately 1.4826
    data = data.copy()
    difference = np.abs(data- np.median(data))
    median_difference = np.median(difference)
    sigma_num = float(sigma_num)
    dev = k * sigma_num
    lowerthresh = np.median(data) - dev
    print ("Lower threshold (method 2):" + str(lowerthresh))
    upperthresh = np.median(data) + dev
    print ("Upper threshold (method 2):" + str(upperthresh))
    detected_lower_outliers = data < lowerthresh 
    print ("Lower outliers (method 2):" + str(detected_lower_outliers))
    detected_upper_outliers = data > upperthresh
    print ("Upper outliers (method 2):" + str(detected_upper_outliers))
    
    # Replaces any outliers with the median
    data[detected_lower_outliers] = np.median(data)
    data[detected_upper_outliers] = np.median(data)
    print ('Data after filtering (method 2):' + str(data))
    return data

# Detects if the data values are above or below an acceptable threshold value, which indicates a potential failure
def detect_failures(data, minimum, maximum):
    data = data.copy();
    minimum = float(minimum)
    maximum = float(maximum)
    detected_failures_min = minimum > data 
    for i, j in enumerate(detected_failures_min):
        if j == True:
            failure_indices.append(i)
    detected_failures_max = maximum < data
    for i, j in enumerate(detected_failures_max):
        if j == True:
            failure_indices.append(i)        
    print ("Index of failures: " + str(failure_indices))       
    print ("Failures below min threshold: " + str(data[detected_failures_min]))
    print ("Failures above max threshold: " + str(data[detected_failures_max]))
    return failure_indices

# Sends email if any failures are detected 
# Code for sending email adapted from https://en.wikibooks.org/wiki/Python_Programming/Email
def send_warning(send, sendpassword, recipient, body, subject):
    server = smtplib.SMTP("smtp.gmail.com", 587)
    msg = MIMEMultipart()
    
    # Sets up connection with gmail server
    try:       
        server.ehlo()
        server.starttls()
        server.ehlo()
    except:
        print ("Error setting up connection.")
    
    # Logs in to gmail server
    sender_username = send
    sender_password = sendpassword	
    server.login(sender_username, sender_password)

    # Composes message headers
    msg['From'] = sender_username
    recipient = recipient.split(',')
    print ("Recipients: " + str(recipient))
    msg['To'] = ", ".join(recipient)
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    # Sends message
    try:
        text = msg.as_string() 
        server.sendmail(sender_username, recipient, text)
        server.close()
        print ("Warning email has been sent.")
    except:
        print ("Email did not reach recipient.")

# Remove outliers from data using median filtering
outlier_dev = parser.get('outlierfilter', 'deviations')

filtered_data = filter_outliers(curr, outlier_dev)

failthresh_min = parser.get('failurethreshold', 'minimum')
failthresh_max = parser.get('failurethreshold', 'maximum')

checkeddata = detect_failures(filtered_data, failthresh_min, failthresh_max)

currenttime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

unit = parser.get('unit', 'unit')

if checkeddata:
    warning_array = []

    warning_array.append("The following errors were detected! \r\n")  
    warning_array.append("Failures detected with values: ")
    print ("checked data" + str(checkeddata))
    for k in checkeddata:
        warning_array.append(str(curr[k]) + str(unit) + " ")
    warning_array.append(" \r\n")
    warning_array.append("Errors were detected at time: " + str(currenttime) + " \r\n")
    warning_array.append("Minimum threshold: " + str(failthresh_min) + " " + str(unit) + " \r\n")
    warning_array.append("Maximum threshold: " + str(failthresh_max) + " " + str(unit) + " \r\n")
    warning = ''.join(warning_array)
    print(warning)
else:
    print("No failures were detected.")
    warning = None

if warning != None:

    email_sender = parser.get('email', 'sender')
    email_password = parser.get('email', 'password')
    email_recipient = parser.get('email', 'recipient')
    email_subject = parser.get('email', 'subject')
    
    send_warning(email_sender, email_password, email_recipient, warning, email_subject)