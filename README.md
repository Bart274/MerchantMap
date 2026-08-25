
# Merchant Map

This tool will allow you to visualize the locations you visited in the game on a standalone map.
It will also contain a page where you can easily track which herds or ruines you have encountered and whether or not you have gentled/excavated them.


## Installation

You need to have git, python3, node and MySQL installed on your server.

### Google Maps Key

This project uses Google Maps. Each instance of Google Maps requires an API key to make it functional. This is quick guide to setting up your own key.

Getting the API Key

1. Go to [Google API Console](https://console.developers.google.com/)

2. If it’s the first time, click ‘Next’ on a bunch of pop-ups or just click somewhere where the pop-ups aren’t

3. Create Credentials

Select a project: Create a project

Project name: Anything you want

Yes/No for email

Yes to agree to ToS

Click create.

4. Get your API Key

Click on Credentials again

Click Create -> API

Choose ‘Browser Key’

Click ‘Create’ and then copy the API Key somewhereKey

5. Enable five Google Maps APIs

5.1. Google Maps Javascript API - Enables Displaying of Map

Click on ‘Library’

Type ‘JavaScript’ in the search box

Choose ‘Google Maps Javascript API’

Click ‘ENABLE’

5.2. Google Places API Web Service - Enables Location Searching

Click on ‘Library’

Type ‘Places’ in the search box

Choose ‘Google Places API Web Service’

Click ‘ENABLE’

5.3. Google Maps Elevation API - Enables fetching of altitude

Click on ‘Library’

Type ‘Elevation’ in the search box

Choose ‘Google Maps Elevation API’

Click ‘ENABLE’

5.4. Google Maps Geocoding API - Enables geocoding and reverse geocoding

Click on ‘Library’

Type ‘Geocoding’ in the search box

Choose ‘Google Maps Geocoding API’

Click ‘ENABLE’

5.5. Google Maps Time Zone API - Enables time zone for a location

Click on ‘Library’

Type ‘Time Zone’ in the search box

Choose ‘Google Maps Time Zone API’

Click ‘ENABLE’

### Downloading the Application
To run a copy from the latest develop branch in git you can clone the repository:

git clone --recursive https://github.com/Bart274/MerchantMap.git

### Installing Modules
At this point you should have the following:

Python 3

pip

MerchantMap application folder

First, open up your shell (cmd.exe/terminal.app) and change to the directory of MerchantMap.

You can verify your installation like this:

```
python --version
pip --version
```

Now you can install all the Python dependencies, make sure you’re still in the directory of MerchantMap:

Windows:

`pip install -r requirements.txt`

Linux/OSX:

`sudo -H pip install -r requirements.txt`

### Building Front-End Assets
In order to run from a git clone, you must compile the front-end assets with node. Make sure you have node installed for your platform:

- Windows/OSX (Click the Windows or Macintosh Installer respectively)
- Linux – refer to the package installation for your flavor of OS”

Once node/npm is installed, open a command window and validation your install:

```
node --version
npm --version
```

Once node/npm is installed, you can install the node dependencies and build the front-end assets:

```
npm install

# The assets should automatically build (you'd see something about "grunt build")
# If that doesn't happen, you can directly run the build process:
npm run build
```

### Basic Launching
Once those have run, you should be able to start using the application, make sure you’re in the directory of MerchantMap then:

`python3 ./runserver.py --help`

Read through the available options and set all the required CLI flags to start your own server. At a minimum you will need to provide a location and a google maps key.

**Once your setup is running, open your browser to http://localhost:5000 and your merchant location will begin to show up! Happy hunting!**


### Updating the Application
MerchantMap is a very active project and updates often. You can follow the latest changes to see what’s changing.

You can update with a few quick commands:

```
git pull
pip install -r requirements.txt --upgrade (Prepend sudo -H on Linux)
npm run build
```
