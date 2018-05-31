# Raspiled #

Raspberry Pi driven RGB LED strips

![Raspiled Web Interface](https://github.com/michaeljtbrooks/raspiled/blob/master/docs/Raspiled_web_interface.png)

### What is this? ###
RaspiLED is a Python based controller for LED strips. It allows you to drive full-colour (RGB) LED strip from a Raspberry Pi, via a very easy to use touch-friendly web interface.

* Control LED strip mood lighting with your smartphone
* Pre-programmed with main colours
* Simulated sunrises and sunsets
* Colour-sequences such as party lighting

Based on [a tutorial from David Ordnung](https://dordnung.de/raspberrypi-ledstrip/): https://dordnung.de/raspberrypi-ledstrip/

*Disclaimer: I am not responsible if you nuke your Raspberry Pi. Do this at your own risk. Although at £30 / $40 a pop it's hardly much of a risk!*

### Requirements ###
1. Python & this repository
2. A network capable Raspberry Pi or Pi Zero W
3. LED strips, we recommend the SMD5050 RGB type. Check out [AliExpress](https://www.aliexpress.com/wholesale?SearchText=smd5050)
4. 3 x MOSFETs 3.3v logic compatible. [I suggest IRLZ34N](https://www.aliexpress.com/wholesale?SearchText=IRLZ34N)
5. Prototyping matrix board / PCBs
6. 4 core RGB LED ribbon cable
7. Female jumper headers so you can connect your Raspberry Pi to your break out board
8. 12V DC power supply to drive the LEDs (many come with one)
9. 5V DC power supply to drive the Raspberry Pi
10. [Pigpio](http://abyz.me.uk/rpi/pigpio/index.html) to provide you with software pulse width modulation
11. (optional) 3 x 100k pull-down resistors (yes, I know the Raspberry Pi can pull down its own pins, but I like to have my own pull-down resistors, which are safe from accidental software command slippage!)


### Hardware circuitry ###
A relatively simple circuit binds the Raspberry Pi to the LED strip. We use three N-type MOSFETs, one for each colour channel (red / green / blue). The MOSFETs are essentially voltage controlled switches, which thanks to their enormous gate to source resistance, protect the Raspberry Pi pins. MOSFETs can also switch at high frequency, which is important as we're using Pulse Width Modulation (PWM), which involves flicking the LED channels on and off very quickly to adjust their brightness.

I followed David Ordnung's recommendation and went with IRLZ34N MOSFETs. These can handle enough current through the drain > source to run several full size LED strips, are switched on fully at 3.3V on the gate (logic high for Raspberry Pis), and can switch on and off fast enough. You do NOT need a base resistor between the MOSFET gate and the Raspberry Pi pin because MOSFETs have a very high Gate > Source resistance (unlike a regular NPN transistor where you would need one).

MOSFET connections:
* Left pin (gate), is connected to a Raspberry Pi GPIO pin
* Middle pin (drain), goes to the colour channel connector on the LED strip
* Right pin (source), is connected to ground

What we're doing is using the Raspberry Pi pins to switch the MOSFET on, thus connecting the negative side of the respective LED colour channel to ground, allowing those LEDs to turn on.

Here's the circuit I used:

![Raspiled circuit](https://github.com/michaeljtbrooks/raspiled/blob/master/docs/Raspiled_breakout_circuit.png)

For clarity, the way the SMD5050 LED strips work is that they take a common 12V power in, and you connect the relevant colour channel to GROUND to switch the LED on. So the pad marked + on the strip goes to 12V. The pads marked R/G/B go to ground via our MOSFETs. Don't try to stick 12V into the R / G / B contact pads on the LED strip, it won't like it.

##### Optional stuff #####
The LED strips take 12V, but the Raspberry Pi is driven by 5V. I didn't want to muck about with two different "wall wart" power supplies, so I bought a little 12V DC to 5V DC buck converter, and used the output of that to power the Raspberry Pi. Btw you CAN power the Raspberry Pi by pumping 5V into its 5V pin, just be aware that this bypasses the thermal fuse. I made sure my 12V power supply was high quality.

You don't need a heatsink for the MOSFETs, unless your house happens to be hotter than the Sahara (literally hotter than 50 degrees Celcius). I've calculated that the MOSFETs can dissipate three times the heat they will generate when on full tilt at 12V, without a heatsink. That said, they do get hot to the touch, so heatsinks are a consideration if you're stuffing them in a tight enclosed space.


### Software Installation ###
1. Get Raspian or Ubuntu running on your Raspberry Pi, with network connectivity working, and install essential packages:
```bash
sudo apt-get install build-essential unzip wget git
```
2. Install pigpio (see http://abyz.me.uk/rpi/pigpio/download.html)
```bash
wget https://github.com/joan2937/pigpio/archive/master.zip
unzip master.zip
cd pigpio-master
make
sudo make install
```
3. Download this *Raspiled* repo to your Raspberry Pi
4. SSH into your Raspberry Pi. Change to the directory where you saved this repo
5. Install python virtual environments
```bash
sudo apt-get install python-pip 
sudo pip install virtualenv
```
6. Create a virtual environment to run Raspiled in, and activate it
```bash
virtualenv ./
source ./bin/activate
```
7. Install this repo's dependencies (may take 1- mins on a Raspberry Pi
```bash
pip install -r ./src/requirements.txt
```
8. Find out your Raspberry Pi's IP address:
```bash
ifconfig
```
9. Copy ./src/raspiled.conf.TEMPLATE to ./src/raspiled.conf so Raspiled knows what settings to use.
10. Modify ./src/raspiled.conf: change the constants for the Pins match the GPIO pins you have connected the LED colour channels to, and change PI_HOST to "localhost". PI_PORT should be left as 8888 as this is what Pigpiod is configured to use.
11. Run the Pigpiod daemon:
```bash
sudo pigpiod
```
12. Run the Raspiled server:
```bash
python ./src/raspiled_listener.py
```
13. On your smartphone / another computer on the same local network, open your web browser and head to: http://<your.raspberry.pi.ip>:9090 e.g. http://192.168.0.33:9090 in my case

##### Optional stuff #####
If you want the Raspberry Pi to boot up and automatically run Raspiled, you can add this command to /etc/rc.local:
```bash
/path/to/your/virtualenv/python /path/to/your/raspiled/src/raspiled_listener.py
```


### Web Interface ###
#### http://<your.raspberry.pi.ip>:9090 ####

Pretty self explanatory. Click a colour to change the LEDs to that colour. Play with the colour wheel and brightness slider to manually control the colour. Press one of the sequence buttons to start the LEDs running that colour sequence. Click "Off" to set the LEDs to black (i.e. no light).

![Raspiled Web Interface](https://github.com/michaeljtbrooks/raspiled/blob/master/docs/Raspiled_web_interface.png)

I've used a very lightweight Python Twisted webserver for this, because I couldn't be bothered with fannying around with configuring Apache2 or Nginx. There's no authentication as this is not supposed to be exposed to the dirty internet WAN.

I've spent a fair bit of time getting the threading right so that you can start and stop sequences without a delay. So while Raspiled is busy running the colour changes of a sequence, it will still respond immediately to new commands, even if it is mid-fade between colours. 


### That's it! ###
Feel free to download the code, dick about with it, make something awesome. I am also keen to have people contribute to this repo, so long as what you've written is readable!

Here are some ideas for improvements:
* Authentication & tokens: so only recognised devices can control the LEDs
* Sound responsiveness: So the LED lights flash to the beat!
* IFTTT events and notifications: e.g. flash green when your smartphone / WhatsApp / Skype rings.
* Binding to other IoT stuff: e.g. flash when someone rings the doorbell or run the NeeNaw USA sequence when your house alarm sounds!
* Scheduled events: e.g. run the sunset sequence over the hour before bedtime
* Holiday mode: turn the lights on for several minutes then off to deter burglars


#### With thanks to ####
* David Ordnung for his [amazing tutorial on driving LED strips from the GPIO pins](https://dordnung.de/raspberrypi-ledstrip/)
* Josue-Martinez-Moreno for contributing better logging, the config file architecture and other very good ideas
