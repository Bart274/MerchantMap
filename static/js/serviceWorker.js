/**
 * Push v1.0-beta
 * ==============
 * A compact, cross-browser solution for the JavaScript Notifications API
 *
 * Credits
 * -------
 * Tsvetan Tsvetkov (ttsvetko)
 * Alex Gibson (alexgibson)
 *
 * License
 * -------
 *
 * The MIT License (MIT)
 *
 * Copyright (c) 2015-2017 Tyler Nickerson
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */
 /* global clients */
'use strict'

function isFunction(obj) {
    return obj && {}.toString.call(obj) === '[object Function]'
}

function runFunctionString(funcStr) {
    if (funcStr.trim().length > 0) {
        // eslint-disable-next-line no-new-func
        var func = new Function(funcStr)
        if (isFunction(func)) {
            func()
        }
    }
}

function findValidClient(clients, origin) {
    var validClient = null
    for (var i = 0; i < clients.length; i++) {
        var client = clients[i]
        if (client.url === origin) {
            validClient = client
            if ('focused' in client && client.focused) {
                return client
            }
        }
    }
    return validClient
}

function sendCenterMapMessage(client, lat, lon) {
    client.postMessage(JSON.stringify({
        action: 'centerMap',
        lat: lat,
        lon: lon
    }))
}

self.addEventListener('message', function (event) {
    self.client = event.source;
    if (event.data && event.data.type === 'UPDATE_BADGE') {
      const count = event.data.count;
      updateBadge(count);
    }
})

self.onnotificationclick = function (event) {
    event.notification.close()

    event.waitUntil(clients.matchAll({includeUncontrolled: true, type: 'window'}).then(function (clientList) {
        var client = findValidClient(clientList, event.notification.data.origin)

        if (client && 'focus' in client) {
            client.focus().then(function (client) {
                sendCenterMapMessage(client, event.notification.data.lat, event.notification.data.lon)
            })
        } else if ('openWindow' in clients) {
            clients.openWindow('/').then(function (client) {
                sendCenterMapMessage(client, event.notification.data.lat, event.notification.data.lon)
            })
        }
    }))
}

self.onnotificationclose = function (event) {
    runFunctionString(event.notification.data.onClose)

    /* Tell Push to execute close callback */
    self.client.postMessage(JSON.stringify({
        id: event.notification.data.id,
        action: 'close'
    }))
}

function updateBadge(count) {
    if ("Notification" in self) {
      if (Notification.permission === "granted") {
          console.log("Notification permission granted.");
      } else if (Notification.permission !== "denied") {
        // We need to ask the user for permission
        Notification.requestPermission().then((permission) => {
          // If the user accepts, let's create a notification
          if (permission === "granted") {
            console.log("Notification permission granted.");
          }
        });
      }
  }
  // Inside a Service Worker, the global is `self`, not `navigator`
  if ('setAppBadge' in self) {
    if (count > 0) {
      self.setAppBadge(count).catch(function (e) {
        console.error('setAppBadge failed:', e);
      });
    } else {
      self.clearAppBadge().catch(function (e) {
        console.error('clearAppBadge failed:', e);
      });
    }
  }
}

self.addEventListener('install', function (event) {
  self.skipWaiting();
});

self.addEventListener('activate', function (event) {
  event.waitUntil(self.clients.claim());
});
