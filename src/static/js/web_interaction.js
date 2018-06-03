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

defaultmainmenu='light'
$('[id="menu_click"]').click(function(){
    if ($(this).attr('name')!=defaultmainmenu){
        $('.main-menu').fadeTo(100, 0, function() {
            $(this).hide();
        });
        $("#"+$(this).attr('name')).show(function(){
            $($(this)).fadeTo(100,1)
        })
        defaultmainmenu=$(this).attr('name')
        $("#menu_content").animate({'width' : 0}, 500);
        $("#menu").animate({'right' : 0}, 500);
        click_check=0
    }
});
