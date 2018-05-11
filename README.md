# Raspiled #

Raspberry Pi driven RGB LED strips

### What is this? ###
RaspiLED is a Python based controller for LED strips. It allows you to drive full-colour (RGB) LED strip from a Raspberry Pi, via a very easy to use touch-friendly web interface.

* Control LED strip mood lighting with your smartphone
* Pre-programmed with main colours
* Simulated sunrises and sunsets
* Colour-sequences such as party lighting

Based on [a tutorial from David Ordnung](https://dordnung.de/raspberrypi-ledstrip/): https://dordnung.de/raspberrypi-ledstrip/


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


### Software Installation ###
1. Get Raspian or Ubuntu running on your Raspberry Pi, with network connectivity working
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
9. Run the Raspiled server:
```bash
python ./src/raspiled_listener.py
```
10. On your smartphone / another computer on the same local network, open your web browser and head to: http://<your.raspberry.pi.ip>:9090






