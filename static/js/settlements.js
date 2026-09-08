var rawDataIsLoading = false

// Raw data updating
var minUpdateDelay = 30000 // Minimum delay between updates (in ms).
var lastRawUpdateTime = new Date()

function showSettlements(data) {
  $('#myTable tbody > tr').remove();
  console.log("fetch settlements");
  if (data != null){
    console.log("got data no position");
    let settlements = data['settlements'].sort(function(a, b) {
      if (b['distance'] > 0) {
        return a['distance'] - b['distance'];
    } else {
      return b['last_scanned'] - a['last_scanned'];
    }
    });
    $.each( settlements, function( key, val ) {
      let name = val['name'];

      if (val['settlement_type']) {
          name = val['settlement_type'] + " " + name;
      }

      let class_string = 'my-new-list';

      let populationStr = val['population'] + " / " + val['max_population'];
      let populationClass = 'population';
      if (val['almost_populated']) {
          populationClass += ' almost_populated';
      }
      if (val['populated']) {
          populationClass += ' populated';
      }

      let financialStr = 'Daily gold: ' + val['daily_gold'];
      let financialClass = 'financial';
      if (val['corruption_days']) {
          financialStr += '<br/>Last visited ' + val['corruption_days'] + ' days ago.';
          if (val['corruption_cost']) {
              financialStr += '<br/>Corruption to pay: ' + val['corruption_cost'];
              financialClass += ' corrupted';
          } else if (val['corruption_days'] >= 10) {
              financialClass += ' almost_corrupted';
          }
      }
      let storageStr = val['stock_count'] + " / " + val['max_storage'];
      let storageClass = 'storage';
      if (val['almost_full']) {
          storageClass += ' almost_full';
      }
      if (val['is_full']) {
          storageClass += ' full';
      }

      let districtStr = 'ID: ' +val['district_id'];

      let culturalStr = 'Cultural score: ' + val['cultural_score'];

      let distance = val['distance'];
      let distance_unit = " m";
      if (distance > 1000) {
        distance = distance / 1000;
        distance = +distance.toFixed(1);
        distance_unit = " km";
      }
      let distance_str = distance + distance_unit;

      let lastvisitedStr = "Not yet visited";
      if (val['last_visited']) {
          lastvisitedStr = moment(val['last_visited']).format('YYYY-MM-DD HH:mm')
      }

      let imgSrc = val['sprite'];
      let imgSrcHtml = '';
      if (imgSrc) {
          imgSrcHtml = '<img src="' + imgSrc + '" class="sprite"/>';
      }

      $( "<tr/>", {
        "class": class_string,
        html: "<td>" + imgSrcHtml + " " + name + " \
                </td><td class='" + populationClass + "'> \
                    " + populationStr + " \
                </td><td class='" + financialClass + "'> \
                    " + financialStr + " \
                </td><td> \
                    " + culturalStr + " \
                </td><td class='" + storageClass + "'> \
                    " + storageStr + " \
                </td><td> \
                    " + moment(val['last_scanned']).format('YYYY-MM-DD HH:mm') + " \
                </td><td> \
                    " + lastvisitedStr + " \
                </td><td> \
                    " + districtStr + " \
                </td><td> \
                    " + distance_str + " \
                </td><td> \
                    " + val['latitude'] + "," + val['longitude'] + " <a target=\"_blank\" href=\"./?lat="+val['latitude']+"&lon="+val['longitude']+"\">View on Map</a> \
                </td>"
      }).appendTo( "tbody" );
    });
    applyFilter();
  }
  $("#loader_placeholder").hide();
}

function getParameterByName(name, url) {
    if (!url) {
        url = window.location.search
    }
    name = name.replace(/[[\]]/g, '\\$&')
    var regex = new RegExp('[?&]' + name + '(=([^&#]*)|&|#|$)')
    var results = regex.exec(url)
    if (!results) {
        return null
    }
    if (!results[2]) {
        return ''
    }
    return decodeURIComponent(results[2].replace(/\+/g, ' ').replace('_', ' ').replace('%27', "'"))
}

function loadRawData() {
    $("#loader_placeholder").show();
    var playeridparam = getParameterByName('playerid')
    return $.ajax({
        url: 'raw_settlements',
        type: 'post',
        data: {
            'playerid': playeridparam
        },
        dataType: 'json',
        beforeSend: function () {
            if (rawDataIsLoading) {
                return false
            } else {
                rawDataIsLoading = true
            }
        },
        complete: function () {
            rawDataIsLoading = false
        }
    })
}

function updateSettlements() {
    lastRawUpdateTime = new Date()
    loadRawData().done(function (result) {
        // Parse result on success.
        showSettlements(result)
    }).always(function () {
        // Only queue next request when previous is over.
        // Minimum delay of minUpdateDelay.
        var diff = new Date() - lastRawUpdateTime
        var delay = Math.max(minUpdateDelay - diff, 1) // Don't go below 1.

        // Don't use interval.
        window.setTimeout(updateSettlements, delay)
    })
}


/*
 * Document ready
 */
$(document).ready(function () {
  loadRawData().done(function (result) {
    showSettlements(result)
    window.setTimeout(updateSettlements, minUpdateDelay)
    window.setInterval(updateLabelDiffTime, 1000)
  })

})

function applyFilter(){
  var td, td_col, resultcount;
  var classes = [];

  $("#myTable tbody tr").show();
  resultcount = 0;
  $("#myTable tbody tr").each(function () {
    var row = $(this).eq(0);
    if (row.is(":visible")) {
        resultcount += 1;
    }
  });
  $("span[id='resultcount']").text(resultcount + " Settlements found.");
}


function lpad(str, len, padstr) {
    return Array(Math.max(len - String(str).length + 1, 0)).join(padstr) + str
}

function getTimeUntil(time) {
    var now = Date.now()
    var tdiff = time - now

    var sec = Math.floor((tdiff / 1000) % 60)
    var min = Math.floor((tdiff / 1000 / 60) % 60)
    var hour = Math.floor((tdiff / (1000 * 60 * 60)) % 24)

    return {
        'total': tdiff,
        'hour': hour,
        'min': min,
        'sec': sec,
        'now': now,
        'ttime': time
    }
}

var updateLabelDiffTime = function () {
    $('.label-countdown').each(function (index, element) {
        var disappearsAt = getTimeUntil(parseInt(element.getAttribute('disappears-at')))

        var hours = disappearsAt.hour
        var minutes = disappearsAt.min
        var seconds = disappearsAt.sec
        var timestring = ''

        if (disappearsAt.ttime < disappearsAt.now) {
            timestring = '(expired)'
        } else {
            timestring = lpad(hours, 2, 0) + ':' + lpad(minutes, 2, 0) + ':' + lpad(seconds, 2, 0)
        }

        $(element).text(timestring)
    })
}
