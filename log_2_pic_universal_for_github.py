#!/home/ltolstoy/anaconda3/bin/python
"""
Universal script, to process data from xxxx_bxx.log file, output png image into the same folder
Reads site specific settings from the site folder/settings.ini
v1 - 5/15/17
v2 - 5/17/17 - use settings.ini instead of settings_pic.ini
v3 - 5/22/17 - use cond_check from csv version, which filters out stuck data. 
    Added check for correctness of timezone.
V4 - ?
v5 - 8/21/17 - change processing to use Corey's library adl, to read values from responses
v6 - 10/2/17 - changed num2date to num2date(epoch2num) ll.424-425 - now matplotlib v2 works this way??
v7 - 11/1/17 - change block so it can be anything between "_b" and "." in filename
	Changed read_data : new SKU mapping to classes, according to new sku_map
v8 - 11/29/17 - new way to use SKUs - use adl from Corey to find a class in get_items, new read_data
v9 - 4/12/18 - move it to Server VM, use python 3.6, pyADL3.5
    fixed line 702, added encoding="latin-1"
"""

import datetime
import os, configparser
import sys
import argparse
from pathlib2 import Path
import matplotlib as mpl
mpl.use('Agg') #TkAgg. Forces matplotlib to not use any Xwindow backend, so it can work from crontab, automatically. Has to be Before any other matplotlib import!
import matplotlib.pyplot as plt
import matplotlib.dates as pd
import pytz
import warnings
warnings.filterwarnings('ignore')
import imp
adl = imp.load_source('adl','/home/ltolstoy/scripts/PyADL/pyadl3.5/adl.py')

    
def get_idx(s, list_of_macs):
    # getting string with data from the device, and checking if mac is in list_of_macs
    # return index in the list_of_macs, or -1 if not there
    # s - whole string \xxxxxx\xxxxxxxxxxx etc
    m = s[20:32] # MAC of converter, 12 bytes
    if m in list_of_macs:
        return list_of_macs.index(m)
    else:
        return -1

def ser2mac(serial):
    serial = serial.upper()
    week = int(serial[:2])
    year = int(serial[2:4])
    letter = ord(serial[4]) - 65
    ser = int(serial[5:])

    prefix = '%06X' % ((week << 18) | (year << 11) | (letter << 6))
    suffix = '%06X' % ser

    return prefix + suffix

def get_list_of_items(block, p_to_logs):
    '''
    block = '302','303',
    p_to_logs - path to folder where log is, like /mnt/data_log/canadian_solar/tmp/
    p_to_struc - Here we find a file structure_xxx.xml, and get list_of_macs, sn, string_name from it
    '''
    import xml.etree.ElementTree as ET
    p_to_struc = os.path.abspath(os.path.join(p_to_logs, os.pardir)) # gets 1 level up, to /mnt/data_log/canadian_solar/
    name_str = '/structure_'+block+'.xml'
    p = p_to_struc + name_str #full path, including file name
    if os.path.exists(p):
        tree = ET.parse(p)
        root = tree.getroot()
        macs = [] #mac addresses
        sns = []  #serial numbers
        stnames =[]  #string names "02.01.01-1"
        skus = []   # SKUs like "31570020-00 C"
        clss = []  # class like str 'Midstring1000Data'
        sm = adl.SkuMap()  # to get class name using adl

        for m in root.iter('String'):
            a1 = m.get('name')
            stnames.append(''.join(a1))
        for m in root.iter('Converter'):
            b = m.get('sn')
            try:
                sns.append(''.join(b))
            except:
                print("Exception in get_list_of_items: can't get sn. Receiving {} instead from {}".format(b, m.attrib))
            a = m.get('mac')
            try:
                macs.append(''.join(a))  # otherwise doesn't work
            except:
                print("Exception in get_list_of_items: can't get mac, probably it was not commissioned. The line is {}. Restoring mac from sn!".format(a, m.attrib))
                a2 = ser2mac(b)      # if no mac exsists in xml, restore it using ser2mac and add anyway
                macs.append(''.join(a2))  # otherwise doesn't work
                print("Restored mac {} from sn {}".format(a2,b))
            c = m.get('sku')
            try:
                c1 = c  #.split()[0]
                skus.append(''.join(c1))
                clss.append(''.join(sm.getDataClassName(c1)))
            except:
                print("Exception in get_list_of_items: can't get sku. Receiving {} instead from {}".format(c, m.attrib))
        print("getting items from structure_{}.xml: got {} items".format(block,  str(len(macs)) ))
        return macs, sns, stnames, skus, clss
    else:
        print("{} doesnt exist, can not work without structure.xml. Exiting now".format( p ))
        sys.exit()



def put_data( existing_data, new_data ):
    """ Gets 2 lines, existing and new
    # put_data( data[c][idx][:], fill_info(one[i]) )
    # check if exisiting_data had '' in every place, if yes (meaning previous fill was bad or first)- put
    # there new_data, if new data is empty in some positions- leave what was there before
    Returns out line, consisting of combination """
    out = [''] * len(existing_data)
    for i in range(0, len(existing_data)): #both lines are 22+2 elements
        if existing_data[i] == '':
            out[i] = new_data[i] # if current position was empty - fill it with new data
            # otherwise leave whatever was there before
            #this is to avoid overwritting good values with new , which might be empty ''
        else:
            out[i] = existing_data[i] # leave whatever was there
    return out # all good        

        
def show_fig2(x1,y1,y2, i_lim, p_to_logs, log_name, t_int, i_av, u_av, p_av, d2, addit_time, addit_noncomm, est, name, tz):
    '''
    Inputs: t, n_nocomm, n_lowcur, i_lim, p_to_logs (to save output image into the same dir)
    Also average I for interval, Uav, and P_av    
    est - depends on timezone from settings.ini
    name - site_name like "ITF"
    tz - timezone like "MST"
    ''' 


    if len(x1) != len(y1):
        print("show_fig_2: different lengths of time seq  and variable seq")
        print("{} vs {} , {}".format(str(len(x1)), str(len(y1)), str(len(y2)))) 
        return -1
    else:
        f, axarr = plt.subplots(5, sharex=True, figsize=(12,3*5))
        plt.xticks(rotation = 15)
        plt.xlabel('Time specific for timezone ' + tz)

        axarr[0].xaxis.set_major_formatter(pd.DateFormatter('%H:%M',est))
        axarr[0].plot_date(x1, y1, 'r-')
        axarr[0].plot_date(addit_time, addit_noncomm, 'k-') #plotting empty interval, where no log records exists
        axarr[0].set_ylim([0, d2+2 ])
        axarr[0].yaxis.grid(True)
        axarr[0].set_title('Number of not-communicating units at '+ name+ ' ' + log_name)
        axarr[1].plot_date(x1, y2, 'b-')
        axarr[1].set_ylim([0, d2 + 1 ])
        axarr[1].yaxis.grid(True)
        axarr[1].set_title('Number of low-current units, with Iout<'+str(i_lim)+'A. Time interval='+t_int+' min.')
        axarr[2].plot_date(x1, i_av, 'g-')
        axarr[2].set_title('Average Current, A')
        axarr[2].set_ylim([0, max(i_av) + 0.5 ])        
        axarr[2].yaxis.grid(True)
        axarr[3].plot_date(x1, u_av, 'k-')
        axarr[3].set_ylim([0, max(u_av)+10 ]) # changed in v9
        axarr[3].yaxis.grid(True)
        axarr[3].set_title('Average Voltage, V')
        axarr[4].plot_date(x1, p_av, 'm-')
        axarr[4].yaxis.grid(True)
        axarr[4].set_title('Average Power, kW')
        axarr[4].set_ylim([0, max(p_av) * 1.1 ])
        
        fname=log_name[:-4]+'_report.png'
        print("Saving plots")
        plt.savefig(p_to_logs + fname, bbox_inches='tight')       
        
        
     
        
def get_ind(lines, t, ts, te, c):
    # Input : # of lines, t - all times, tsstart, tend, c- interval number
    #Output - sequential indexes
    #print "\nInterval " + str(c)
    ind = [i for i in range(lines) if t[i]>=ts and t[i]<te]  #indexes of sc in time range
    #print ind

    if len(ind)>1:
        i=1
        while i < len(ind):
            if ind[i] != ind[i-1]+1 or t[ind[i]] <= t[ind[i-1]]:
                '''print "get_ind: not sequential indexes found or time next  is less than previous:"
                print i-1, i, ind[i-1], ind[i]
                print "time of " + str(ind[i-1]) + " : " + "{: %X}".format(mdates.num2date(t[ind[i-1]]))
                print "time of " + str(ind[i]) + " : " + "{: %X}".format(mdates.num2date(t[ind[i]]))
                print len(ind), ind
                '''
                del ind[i]
                i += 1
            else:
                #print i                
                i += 1
    #here we are done with cleaning from non-sequential elements
    return ind

def read_data(resp, skus, list_of_macs, clss, what):
    """
    Function to read and interpret response string using corresponding class from adl (by looking at SKU)
    :param resp: response line like "|05FEA9|15CB9A59C1C45882800000C6C3999F71900507722A07C503E9033A001D9B8EC8"
    :param skus: list of SKU - to find which class to use to read resp
    :param what: what I need to return: UTC, All, etc
    :param clss: list of data classes corresponding to SKU : like 'Midstring1000Data'
    :return:  some value requested, like UTC, ALL, SHORT, or -1 if something wrong
    """
    if resp[0] =='|' and resp[7]=='|':
        mac = resp[20:20+12]                    #selecting mac
        ind = get_idx(resp, list_of_macs)       #finding index of this mac
        if ind != -1:                           #mac exists in the list
            sku = skus[ind]                     #use corresponding SKU
            cls = clss[ind]  # str like 'Midstring1000Data', or 'SKU not found'
            if cls == 'ModuleData':
                m = adl.ModuleData()
                m.update(resp)
            elif cls == 'Midstring600Data':
                m = adl.Midstring600Data()
                m.update(resp)
            elif cls == 'Midstring1000Data':
                m = adl.Midstring1000Data()
                m.update(resp)
            elif cls == 'Midstring1500Data':
                m = adl.Midstring1500Data()
                m.update(resp)
            else:
                cls = "UnknownData"
                return -1

            # Here we analyze available public attributes in the current class.  Not all attributes are available everywhere!
            try:
                ch = str(m.ch)
            except:
                ch=''
            try:
                bunch = str(m.bunch)
            except:
                bunch = ''
            try:
                timeslot = str(m.timeslot)
            except:
                timeslot = ''
            try:
                mpp = str(int(m.mpp))
            except:
                mpp = ''
            try:
                mod = str(int(m.mod))
            except:
                mod = ''
            try:
                vout = m.vout
            except:
                vout = ''
            try:
                vin1 = m.vin1
            except:
                vin1 = ''

            try:
                vin = m.vin
            except:
                vin = ''
            try:
                iout = m.iout
            except:
                iout = ''
            try:
                vin2 = m.vin2
            except:
                vin2 = ''
            try:
                text = m.text
            except:
                text = ''
            try:
                iin2 = m.iin2
            except:
                iin2 = ''
            try:
                iin1 = m.iin1
            except:
                iin1 = ''
            try:
                vref = m.vref
            except:
                vref = ''
            try:
                gw_off = m.gw_off
            except:
                gw_off = ''
            try:
                gw_rssi = m.gw_rssi
            except:
                gw_rssi = ''
            try:
                ed_off = m.ed_off
            except:
                ed_off = ''
            try:
                ed_rssi = m.ed_rssi
            except:
                ed_rssi = ''
            try:
                ov = m.ov
            except:
                ov = ''
            try:
                oc = m.oc
            except:
                oc = ''
            try:
                pin = m.pin
            except:
                pin = 0

            if what == "UTC":
                if type(m.utc) is int:
                    return m.utc
                else:
                    #print("Alarm! Smth wrong here. Resp={}".format(resp))
                    pass

            elif what == "SHORT":       #only Mac, Vout, Iout - for the picture
                return mac, vout, iout
            else:
                if cls != "ModuleData":
                    try:
                        return (mac, ch, bunch, timeslot, mpp, mod,
                            vout, vin1, iout, vin2,
                            text, iin2, iin1, vref,
                            gw_off, gw_rssi, ed_off, ed_rssi, ov, oc)
                    except AttributeError:
                        print("AttributeError in read_data. Class: {} Problem string:{}".format(cls,resp))

                else :
                    iin= round(m.pin/(m.vin + 0.0001),3) # calculate Iin and round it. Use instead of Iin1,Iin2
                    return (mac, '0', bunch, timeslot, mpp, mod,
                        m.vout, m.vin, m.iout, m.vin,
                        text, iin, iin, vref,
                        gw_off, gw_rssi, ed_off, ed_rssi, ov, oc)
                        # as there is no vin2, iin2, i use vin, and calculate iin=Pin/(vin+0.001) to avoid division by 0
        else:  # mac not found case
            return -1


def cond_check(l, t, list_of_macs, skus, clss):
    """
    To check all conditions before creating a record in data_gw
    l - 1 SC, ie request and ED responces part of the log, corresponding to 1 SC
    t- number of supercycle
    list_of_macs - to check that current mac is in the list, not some garbage
    skus - list of corresponding SKUs from structure.xml, need it to correctly read data
    returns good_response - list of request, and filtered (by time_difference) responses from ED
    """
    one = l.split()

    if (len(l) >= 127 and t > 0 and len(one) > 11
        and one[0] == "MAC:" and len(one[1]) == 12
        and one[2] == "Ch:" and len(one[3]) <= 3
        and one[4] == "T:" and len(one[5]) <= 4
        and one[6] == "UTC:" and len(one[7]) == 10
        and one[8] == "ms:" and len(one[9]) <= 3
        and one[10][0] == '|' and one[10][7] == '|'): # this and one[10][0] == '|' and one[10][7] == '|' is important! To avoid text messages
        try:
            request_utc = int(one[7])  # change request UTC to int
        except:
            request_utc = 0  # change request UTC to int
        good_resp = [x for x in one[:10]]  # put request part of SC into list, then add filtered good responses
        # tdf = []
        for response in one[10:]:
            rightchars = set(['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'A', 'B', 'C', 'D', 'E', 'F','|'])  # only those chars are acceptible
            respset = set(response)
            if (len(response) == 72 and response[0] == '|' and response[7] == '|'
                 and respset.issubset(rightchars)):  # check for correct beginning, it doesn't start with '*', and bad chars
                response_utc = read_data(response, skus, list_of_macs , clss, 'UTC') # getting only UTC from response
                if response_utc != -1:
                    tdifference = request_utc - response_utc  # diff in sec between request time and response time for 1st responded device
                    if tdifference == 0 and get_idx(response, list_of_macs) != -1:  # means response is from the same time as request, and mac exists in the list
                        good_resp.append(response)
                    else:
                        # don't include response with old UTC into output, to avoid repetitions
                        pass
                else:   #if response_utc == -1
                    pass
            else:
                pass #skip responses wrongly formatted, with unreadable chars, started with '*'

        return good_resp
    else:  # short SC block, or corrupted request header
        return -1

    
def round_to_2min(t, t_int):
    """
    Changes t so number of minutes is even: 0, 2, 4, 6, etc, and nulls any seconds
    Inputs: t - time (int timestamp, like 1471467015), 
    t_int - str. time interval  (2, 3, 5 min)
    Returns int value
    """
    reminder = t % (60 * int(t_int)) # so from 14714670015 we getting 15
    t_rounded = t - reminder
    
    return int(t_rounded)

def prepare_plot_data(data_gw, data,d2, p_to_logs, fname, start_time, finish_time, est, name, tz):
    '''
    For kee_v2 and UP. process time as timestamp (save year, month, etc). time is in data_gq[i][0] - int value
    Receives data_gw, data, d2- number of MACs in data
    prepares data to be send to show_fig function
    # start_time, finish_time - strings like '0001, '2359' - ignored for now
    est -
    name - site name for show_fig, like "ITF"
    tz - timezone like "MST" for show_fig
    '''
    #str_time = pd.date2num(datetime.datetime.strptime(start_time[0:2]+':'+start_time[2:4]+':00','%H:%M:%S'))  # start time for all
    #end_time = pd.date2num(datetime.datetime.strptime(finish_time[0:2]+':'+finish_time[2:4]+':00','%H:%M:%S'))  # start time for all
    
    t = [ data_gw[i][0] for i in range(len(data)) ] # t - int timestamps like 1471467015
    t_int = '2' # time interval, 2 min
    dt = int(t_int) *60  #120 sec
    if t[-1] - t[0] > 60*60*24:
        print("prepare_plot_data error: time in the log beginning and end is longer than one day! Can't plot such long intervals. Exiting now")
        print("t beginning: {}".format(pd.num2date(pd.epoch2num(t[0]))))
        print("t ending: {}".format(pd.num2date(pd.epoch2num(t[-1]))))
        sys.exit()

    
    lines = len(data)
    n_nocomm = [0 for i in range(lines)] # to store number of not communicating devices for each SC
    n_lowcur = [0.0 for i in range(lines)] # to store number of devices with low current values for each SC
    u_av = [0.0 for i in range(lines)] # average Vout
    i_av = [0.0 for i in range(lines)] # average Iout
    p_av = [0.0 for i in range(lines)] # average Pout
    i_lim =0.06 # threshold for current, if less - count it as not-working

    #ts = t[0] #start interval time
    #ts = round_to_2min(t[0], t_int) if round_to_2min(t[0], t_int) >= str_time else str_time  # choose max of t[0] and str_time, so start later
    ts = round_to_2min(t[0], t_int) #int
    te = ts + dt #end interval time, int
    c=0  #count intervals
    ts_prev = ts
    te_prev = te
    #c_lim = (t[-1]-t[0])/(int(t_int)*60)      # limit number of periods to detect infinite loop, if too many - exit!
    c_lim = 2*24*60/int(t_int)
    addit_time=[] # save ts, te of noncomm period
    addit_noncomm=[] # save number d2 of noncomm devices
    addit_sc=[] #save sc when there no daa points (total noncommuniaction period)
    while te <= t[-1] and c < c_lim: #while not exeeding time and number ot t intervals is reasonable low
        c = c + 1
        '''print '\r'+ str(c) + " ts: " + str(ts) + ' or ' + "{: %X}".format(pd.num2date(ts)) + " ---  te: " + "{: %X}".format(pd.num2date(te)),
        sys.stdout.flush()'''
        if c >= c_lim-2:
            print(" Exit from endless loop. Now intervals number is {}".format( str(c))) 
            print("Stuck at ")
            print("ts: {}".format( "{: %X}".format(pd.num2date(pd.epoch2num(ts))) )) # "ts: " + "{: %X}".format(pd.num2date(pd.epoch2num(ts)))
            print("te: {}".format( "{: %X}".format(pd.num2date(pd.epoch2num(te))) ))
            sys.exit()
        ind = get_ind(lines, t, ts, te, c)
        # ind = [i for i in range(lines) if t[i]>=ts and t[i]<te]  #indexes of sc in time range
        if len(ind) < 1:  # no sc gets into the interval
            #print "Interval doesnt have any data points: " + str(c) 
            '''print "ts: " + "{: %X}".format(pd.num2date(ts))
            print "te: " + "{: %X}".format(pd.num2date(te))'''
            ts = ts+dt
            te = ts+dt   #just move interval further
            #addit_time.append(ts)
            addit_time.append(ts)
            addit_time.append(te)
            #addit_time.append(te)
            #addit_noncomm.append(0)
            addit_noncomm.append(d2)
            addit_noncomm.append(d2)
            addit_sc.append(c)
            #addit_noncomm.append(0)# filling 2 additional noncomm points
        else:
            if len(ind) == 1: #special case of just one sc in interval
                #print "interval has only one SC : " + str(c) 
                '''print "ts: " + "{: %X}".format(pd.num2date(ts))
                print "te: " + "{: %X}".format(pd.num2date(te))
                '''
                ts = ts +dt  # if only one sc in time range, assign new ts by just increasing it by dt
                te = ts +dt
                f_n = [0 for i in range(d2)]  #flags for all macs no-comm
                #f_l_1 = [0 for i in range(d2)]  #flags for all macs low_curr - even devices
                #f_l_2 = [0 for i in range(d2)]  #flags for all macs low_curr - odd devices
                f_l = [0 for i in range(d2)]  #combine flag for pairs of midstrings
                curr_sum = 0  #sum of currents
                curr_count = 0 #counter of how many devices registered
                volt_sum = 0 #sum of sums in complete pairs, where both ED answer
                volt_count = 0 # number of good pairs
                #data :mac, Vout, Iout, Pout
                for j in range(d2) : #all macs check.  data dimentions are lines x 30 x 3 
                    k = ind[0]  # only one sc, no need for cycle
                    if data[k][j][0] != '' : #not-empty MAC, means  communication happened
                        f_n[j] = 1 #rise flag, from 0 to 1, if comm happened
                    if data[k][j][2] != '' : #if notempty current value, check for threshold
                        if float(data[k][j][2]) < i_lim :
                            f_l[j] = 1  #found low current event
                    # deal with each current:
                    if data[k][j][2] != '':
                        curr_sum += float(data[k][j][2]) #increase sum of current values
                        curr_count += 1 #increase counter
                        volt_sum += float(data[k][j][1])
                        volt_count +=1
                n_nocomm[ind[0]] = d2-sum(f_n)   # counting all nocomm events in range of interest
                n_lowcur[ind[0]] = sum(f_l) 
                if curr_count != 0 and volt_count != 0:
                    i_av[ind[0]] = curr_sum / curr_count
                    u_av[ind[0]] = volt_sum / volt_count
                    p_av[ind[0]] = d2 * 0.001 * i_av[ind[0]] * u_av[ind[0]] # in kW
                else:
                    print("\ncurr_count or volt_count is 0, prevent dev by 0")
            else:  #normal case of many sc in interval
                if t[ind[-1]] > ts: # bcs can be time at the end of interval less than at the beginning
                    #ts = t[ind[-1]] #new start of interval is the time of the last sc in interval
                    ts = ts +dt
                    te = ts +dt
                else:
                    ts = ts +dt
                    te = ts +dt
                '''print "Normal interval with many SC : " + str(c) 
                print "ts: " + "{: %X}".format(pd.num2date(ts))+'   ',
                print "te: " + "{: %X}".format(pd.num2date(te))  '''    
                f_n = [0 for i in range(d2)]  #flags for all macs no-comm
                #f_l_1 = [0 for i in range(d2)]  #flags for all macs low_curr - even devices
                #f_l_2 = [0 for i in range(d2)]  #flags for all macs low_curr - odd devices
                f_l = [0 for i in range(d2)]  #combine flag for pairs of midstrings
                
                curr_sum_int = 0  #sum of average currents for interval
                curr_count_int = 0 #counter for interval
                volt_sum_int = 0 #sum of aver voltages for interval
                volt_count_int = 0 # number of aver volt for interval
                for j in range(d2) : #all macs  data dimentions are lines x 30 x 3 
                    for k in range(ind[0],ind[-1]): #Looking in lines interval corresponding to dt min.
                        if data[k][j][0] != '' : #not-empty MAC, means  communication happened
                            f_n[j] = 1 #rise flag, from 0 to 1, if comm happened
                        if data[k][j][2] != '' : #if notempty current value, check for threshold
                            if float(data[k][j][2]) < i_lim :
                                f_l[j] = 1            
                n_nocomm[ind[0]:ind[-1]+1] = [d2-sum(f_n) for z in n_nocomm[ind[0]:ind[-1]+1] ]  # add 1 for all nocomm in range of interest
                n_lowcur[ind[0]:ind[-1]+1] = [sum(f_l) for z in n_lowcur[ind[0]:ind[-1]+1] ]
                # Now deal with u_av, i_av                
                for k in range(ind[0],ind[-1]):
                    curr_sum = 0  #sum of currents
                    curr_count = 0 #counter of how many devices registered
                    volt_sum = 0 #sum of voltages of ED answered
                    volt_count = 0 # number ED answered
                    for j in range(d2): # for each sc in interval
                        if data[k][j][2] != '':
                            curr_sum += float(data[k][j][2]) #increase sum 
                            curr_count += 1 #increase counter
                        if data[k][j][1] != '':    
                            volt_sum += float(data[k][j][1])
                            volt_count +=1   
                    if curr_count != 0 and volt_count != 0:
                        curr_sum_int += curr_sum / curr_count
                        curr_count_int += 1
                        volt_sum_int += volt_sum / volt_count
                        volt_count_int += 1
                    #else:
                        #print "For interval "+ str(c)+ " curr_count or volt_count is 0, prevent dev by 0"           
                
                if curr_count_int != 0:
                    i_av[ind[0]:ind[-1]+1] = [curr_sum_int / curr_count_int for z in i_av[ind[0]:ind[-1]+1] ]
                    #print "Current averaged for interval is " + str(curr_sum_int / curr_count_int)
                else:
                    print("curr_count_int is 0")
                if volt_count_int != 0:
                    u_av[ind[0]:ind[-1]+1] = [volt_sum_int / volt_count_int for z in u_av[ind[0]:ind[-1]+1] ]
                    #print "Voltage averaged for interval is " + str(volt_sum_int / volt_count_int)
                else:
                    print("volt_count_int is 0")
                n = ind[0]
                p_av[ind[0]:ind[-1]+1] = [d2*0.001 * u_av[n] * i_av[n] for z in p_av[ind[0]:ind[-1]+1] ] #as V is averaged per pair, and current per 15 string
                #print "Power averaged for interval is " + str(d2/2 * u_av[n] * i_av[n])  
        if ts_prev == ts and te_prev == te:
            print("Critical situation, time interval was not changed, endless loop starting interval {}".format(str(c) ))
            sys.exit()                
        ts_prev = ts #check that time really changes
        te_prev = te
 
    a_time = []
    a_noncomm = []
    a_time_converted = []

    if len(addit_time)>0: 
        [a_time, a_noncomm] = make_addit(addit_time, addit_noncomm, addit_sc )    # Adding first and last elements to make it go to 0, and filling in gaps in no-comm seq to create "gates"
        a_time_converted = [pd.date2num(datetime.datetime.fromtimestamp(int(a_time[i]), est)) for i in range(len(a_time))]
        
    #Now need to convert t, a_time into matplotli format
    t_converted = [pd.date2num(datetime.datetime.fromtimestamp(int(t[i]), est)) for i in range(len(t))] #from 1471467015 to datetime.datetime, to matplotlib time date number 736193.6319791666
    #show_fig2(t, n_nocomm, n_lowcur,i_lim, p_to_logs, fname, t_int, i_av,u_av,p_av, d2, a_time, a_noncomm) #last values are empty or notcorrect! So sent all but last   
    show_fig2(t_converted, n_nocomm, n_lowcur,i_lim, p_to_logs, fname, \
              t_int, i_av,u_av,p_av, d2, a_time_converted, a_noncomm, est, name, tz)
    #http://stackoverflow.com/questions/4485607/matplotlib-plot-date-keeping-times-in-utc-even-with-custom-timezone


def make_addit(addit_time, addit_n, addit_sc ):
    # gets seq addit_time(ts, te),
    # num = number of noncomm devices (d2 actually, all devices in block)
    # addit_sc - seq of SC numbers, when there were no communication, ie no data points
    # Insert 0 points to make seq usefull
    if len(addit_time) != 0:  # means there is empty sc region
        c = 0 # need to add it for every gap filled
        for i in range(len(addit_sc) - 1):
            if addit_sc[i] + 1 != addit_sc[i+1]:
                te = addit_time[i*2 + 1 +c]
                ts = addit_time[i*2 + 2 +c] 
                #print i, te, ts
                addit_time.insert(i*2 + 2+c, te )
                #print addit_time
                addit_time.insert(i*2 + 3+c, ts )
                #print addit_time
                addit_n.insert(i*2 + 2+c,0)  
                #print addit_n
                addit_n.insert(i*2 + 3+c,0)
                #print addit_n
                c += 2  # need to shift positions by this value every time i insert
        # now include 1st and last 0
        addit_time.insert(0,addit_time[0])
        addit_time.insert(len(addit_time),addit_time[-1])
        addit_n.insert(0,0)
        addit_n.insert(len(addit_n), 0)
        return [addit_time, addit_n]
    else: 
        return [ [], [] ]

def get_settings(path):
    # Reads settings from file settings.ini (from path)
    # path = "/mnt/data_log/itf/settings.ini"
    # Returns timezone , site name
    config = configparser.ConfigParser()
    config.read(path)
    blocks = config.options("Settings")
    return (config.get("Settings", "tz"),
            config.get("Settings", "name"))
    
# main part
def main():  
    parser = argparse.ArgumentParser(description='This is a script to extract data from log file created by SDAG to plots. ')
    parser.add_argument('-i','--input', help='Input log file with path to it, like /path/to/log/cm150101_b1.log',required=True)
    #parser.add_argument('-o','--output',help='Output file name', required=True)
    parser.add_argument('-s','--start', type=int, help='Start time to have in output, like 1334 (means 13:34 or 1:34pm), default 0001')
    parser.add_argument('-f','--finish', type=int, help='Finish time to have in output, like 1934 (means 19:34 or 7:34pm), default 2359')
    args = parser.parse_args()
    #save output csv to the same folder
    if args.start: #if exsist start time
        start_time = str(args.start).zfill(4) #padding it to 4 chars length with zeros in front
    else:
        start_time = '0001' #default start time value 00:01
    if args.finish:
        finish_time = str(args.finish).zfill(4) #padding it to 4 chars length with zeros in front
    else:
        finish_time = '2359'
    print("Time range selected for output: {}:{}-{}:{}".format(start_time[0:2], start_time[2:4],finish_time[0:2], finish_time[2:4])) 
    p2set = str(Path(args.input).parents[1])+'/' #ex '/mnt/data_log/itf'

    if os.path.exists(p2set):
        if os.path.exists(p2set+"settings.ini"):
            tz, site_name = get_settings(p2set+"settings.ini")
            if tz in pytz.all_timezones:
                est = pytz.timezone(tz)
            else:
                print("Time zone in settings.ini file is not existing! Can't continue, exiting now")
                sys.exit()
            print ("Using settings timezone:{} site_name:{}".format(tz, site_name))

        else:
            print("Can't find settings.ini file in folder {} Can't continue, exiting now.".format( p2set))
            sys.exit()
    else:
        print("Can't find working folder {} Can't continue, exiting now.".format( p2set ))
        sys.exit()

    if os.path.exists(args.input):
        fname = os.path.basename(args.input)            #getting log filename
        p_to_logs = os.path.dirname(args.input)+'/'     #getting log path
        #p_to_csv = p_to_logs
        print("Working on file {} from {}".format(fname, p_to_logs)) 
    else:
        print("File not found at {}".format(args.input))
        print("Exiting script, can't work without log file as input")
        sys.exit()

    block = fname[fname.find('_b') + 1:fname.find('.')]  # Either b1,b2,b3 or b4, or b301_2...b508
    print("Found block {}, all right, continuing".format(block ))
        
    list_of_macs, sns, stnames, skus, clss= get_list_of_items(block, p_to_logs)  # all good macs, SNs, stringnames, SKUs
    #d2 = get_good_sc(p_to_logs + fname) #mostly counting not-empty SuperCycles, d2.
    d1 = 3 #Mac, Vout, Iout - use read_data(resp, skus, list_of_macs , 'SHORT') to fill it
    d2 = len(list_of_macs) #83
    d3 = 1 #SC count. Can get full, or allocate dynamically. 
    #For now will be dynamically getting more as we need space for new sc
    
    data = [[['' for k in range(d1)] for j in range(d2)] for i in range(d3)] #3D volume to put all data , 22 x c x 83
    #22 x 83 x 1179 later
    data_gw = [['' for k in range(4)] for j in range(1)] # 4 x 1179 - to save GW params from ss header line: B0 Ch, Temper, Time
    utct_prev=0
    utct=0
    with open(p_to_logs + fname,'r',encoding="latin-1") as fn:
        ss= fn.read().split("=>")   
        c = 0 # counting good, not empty time lines
        for t, l in enumerate(ss):  #t- counting  every sc block, good or bad
            one = cond_check(l, t, list_of_macs, skus, clss)  # one - list ,one filtered SC, consists of request [:10] and responses [10:]
            if one != -1:
                # check for UTC: must be more than previous
                utct = int(one[7])
                if utct > utct_prev: # if current time is more than previous, meaning no overlaps in log

                    try:
                        data_gw[c][0] = int(one[7]) #now save time in full timestamp
                        #was datetime.datetime.fromtimestamp(int(one[7])).strftime('%H:%M:%S')
                    except ValueError :
                        print("ValueError: Something wrong with line header (missing values?): ")
                        data_gw[c][0] = ''
                    except IndexError:
                        print("IndexError: something wrong with counter c={}".format(c))
                        print("one={}".format(one))
                        #print "c=",c
                        print("while length of data is {}".format(len(data_gw) ))
                        pass

                    try:
                        data_gw[c][1] = one[9] #ms
                    except IndexError:
                        data_gw[c][1] = ''
                        print("IndexError: Something wrong with line header (missing values?): ")
                        print(one)

                    try:
                        data_gw[c][2] = str((int(one[3])+4)/10) # Ch: gives channels 1-25 instead 6,16,26,- up to 246
                    except ValueError:
                        data_gw[c][2] = ''

                    data_gw[c][3] = str(one[5]) # T:
                    data_gw.append(['','','',''])  # expanding array, add new layer for new sc
                    #filling one layer, one SC set of devices, up to 83
                    for i in range( 10,len(one) ): # for each left elements of the chunk, which are each device line
                        idx = get_idx(one[i], list_of_macs)  #finding index of the mac in the list_of_macs
                        if idx != -1 and idx<len(list_of_macs):  # means if mac is in list, not just some broken string
                            data[c][idx][:] = put_data( data[c][idx][:], read_data(one[i], skus, list_of_macs, clss, "SHORT"))
                            # check if data[c][idx][:] had '' in every place, if yes - put
                            # there data, if new data is empty - leave what was there before
                        else:
                            '''print "Some problems with string? idx=" + str(idx)
                            print one[i]
                            print "MAC: " + one[i][20:32]+ " not in list."
                            '''
                    data.append([['' for k in range(d1)] for j in range(d2)]) #adding the whole layer 3x83 for the next
                    #
                    utct_prev = utct
                    #
                    c += 1  # increasing good time lines counting, aka SC

                #if c%3000==0:
                    #print '\rGood SC:' + str(c),
                    #sys.stdout.flush()

                #end if
            #end if
         #end for loop
    #end with


    # at this point the whole data array is filled, can make plots with data
    #print "\n"
    if (len(data)>1 and len(data_gw)>1):
        prepare_plot_data(data_gw[:-1], data[:-1], d2, p_to_logs, fname, start_time, finish_time, est, site_name, tz) #send al but last element of data (bks they are empty)
    else:
        print("No good data to process in the log. Early morning or wrong structure.xml file?")
        
    print(" All done! Exiting log_2_pic_universal script...")
    #text_file.close()
    #sys.exit()

if __name__ == "__main__": main()
