#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    Raspiled - LED strip alarm control from Raspberry Pi!

    @author: Josue Martinez Moreno
"""

import schedule
import time
import logging
import sys
import subprocess


logging.basicConfig(format='[%(asctime)s RASPILED] %(message)s',
                    datefmt='%H:%M:%S',level=logging.INFO)

class RaspiledControlAlarm(object):
    def __init__(self,*args,**kwargs):
        self.led_strip = LEDStrip()
        self.hour = hour
        self.temp_0 = int(t_0)
        self.temp_n = int(t_1)
        slef.factor = fudge_factor 
        self.frequency = freq
        self.seconds = seconds
        self.milliseconds = milliseconds
    
        if self.temp_0 > self.temp_1:
            self.temp_step = -100
            self.x_start = 0
            self.x_step_amount = 1
        else:
            self.temp_step = 100
            self.x_start = 60
            self.x_step_amount = -1

    def dayly_alarm(t):
        target_time = self.led_strip.clean_time_in_milliseconds(self.seconds, self.milliseconds, default_seconds=1, minimum_milliseconds=1000)
        z_factor = (target_time*FUDGE_FACTOR) / 2.564949357
        x_step = x_start
        t1 = time.time()

        logging.info('Alarm running at {}'.format(self.hour))
        #And run the loop
        check = True #We only check the current values on the first run
        for temp in xrange(temp_0,temp_n,temp_step):
             if self.led_strip._sequence_stop_signal: #Bail if sequence should stop
                 return None
             k = u"%sk" % temp
             self.led_strip.fade(k, fade_time=((100+z_factor)/(65-x_step)), check=check) #ms, slows down as sunset progresses
             x_step += x_step_amount
             check=False
        return

    def schedule_alarm(self):
        if self.frequency=='dayly':
            schedule.every().day.at(self.hour).do(self.dayly_alarm)
        else:
            pass

        while True:
            schedule.run_pending()
            time.sleep(1) # wait one minute
