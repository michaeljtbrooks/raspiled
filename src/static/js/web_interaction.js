/**
* 
* web_interactions.js
* 
* 	Web routines to support Raspiled interactions
*/

// Menu interface

var click_check = 0;
var menu = document.getElementById('menu');
var menucontent = document.getElementById('menu_content');

menu.style.cursor = 'pointer';

var mousePosition;
var offset = [0];
var div;
var isDown = false;

$.fn.animateRotate = function(angle, duration, initialangle, background, easing, complete) {
  return this.each(function() {
    var $elem = $(this);

    $({deg: initialangle}).animate({deg: angle}, {
      duration: duration,
      easing: easing,
      step: function(now) {
        $elem.css({
            transform: 'rotate(' + now + 'deg)'         
         });
          if (background == 0){
              $elem.css({
                  background: '#5DADE2'         
              });
          }
          else if (background == 1){
              $elem.css({
                  background: '#fff'         
              });
          }
      },
      complete: complete || $.noop
    });
  });
};

document.body.appendChild(menu);

menu.addEventListener('mousedown', function(e) {
    isDown = true;
    offset = [
        menu.offsetLeft-e.clientX,
    ];
}, true);

document.addEventListener('mouseup', function() {
    isDown = false;
}, true);

document.addEventListener('mousemove', function(event) {
    event.preventDefault();
    widthpage=$(window).width()
    
    if (isDown) {
        mousePosition = {
            x : event.clientX,
        };
        if(((widthpage-mousePosition.x)) <= (widthpage*0.25)) {  
            menu.style.right = (widthpage-mousePosition.x) + 'px';
            menucontent.style.width=(widthpage-mousePosition.x) + 'px';
            percent=(widthpage-mousePosition.x)/(widthpage*0.25)

            if(mousePosition.x >= widthpage-widthpage*0.029){
                menu.style.right = 0 + 'px';
                menucontent.style.width= 0 + 'px';
                click_check=0
            }
        }
        else if(((widthpage-mousePosition.x)) >= (widthpage*0.25) ){
            menu.style.right =  (widthpage*0.25) + 'px';
            menucontent.style.width= (widthpage*0.251) + 'px';
            click_check=1
        }
    }
}, true);


$(document).ready(function(){
$("#menu").click(function() {
    widthpage=$(window).width()
    if (click_check==0){
        $("#menu_content").animate({'width' : (widthpage*0.251)}, 500);
        $("#menu").animate({'right' : (widthpage*0.25)}, 500)
        click_check=1
    }
    else{
        $("#menu_content").animate({'width' : 0}, 500);
        $("#menu").animate({'right' : 0}, 500);
        click_check=0
    }
});
});

// Clicking a menu item
var currently_selected_page='light';  // 'light' is our default page
$('.menu_click').click(function(e){
    var $clicked_menu_item = $(this);
    var clicked_menu_item_section_name = $(this).attr("name");
    if ($clicked_menu_item.attr('name') != currently_selected_page){
        var $selected_page_container = $("#"+clicked_menu_item_section_name);
        var $other_page_containers = $(".main-menu").not("#"+clicked_menu_item_section_name);
        $other_page_containers.fadeTo(100,0);  // Fade out from view
        $selected_page_container.show(function(){
            $(this).fadeTo(100,1);
        });
        $other_page_containers.hide(0);  // Properly hide from DOM so they don't intercept touch events

        currently_selected_page = clicked_menu_item_section_name;

        // Hide off the main menu now an item has been selected
        $("#menu_content").animate({'width' : 0}, 500);
        $("#menu").animate({'right' : 0}, 500);
        click_check=0;

    }
});


// Updates the time on the Alarm screen to the current time
var timeInterval = setInterval(function() {
  TimeClock();
}, 1000);

function TimeClock() {
  var d = new Date();
  document.getElementById("clock").innerHTML = d.toLocaleTimeString();
}


function TimeStringToTime(timestring){
    // Converts a time string from sunrise-sunset into an interpretable string
    var timeparts = timestring.split(":");
    if(timestring.includes("PM")){
        var hours = Number(timeparts[0]) + 12;
    } else {
        var hours = Number(timeparts[0]);
    }
    var minutes = Number(timeparts[1]);
    return hours+":"+minutes;
}

