/**
* 
* Raspiled.js
* 
* 	jQuery routines to support Raspiled
*/


//Debouncing function. Rate limits the function calls
function debounce(func, wait, immediate) {
    var timeout;
    return function() {
        var context = this, args = arguments;
        var later = function() {
            timeout = null;
            if (!immediate) func.apply(context, args);
        };
        var callNow = immediate && !timeout;
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
        if (callNow) func.apply(context, args);
    };
};
function init_colourpicker(current_hex){
	//Initialises the colourpicker to the specified colour, or black
	current_hex = current_hex || "#000000";
	
	var COLOR_PICKER_WIDTH_PROPORTION = 0.9;
    var COLOR_PICKER_HEIGHT_PROPORTION = 0.5;
    
    var target_width = $(window).outerWidth(true) * COLOR_PICKER_WIDTH_PROPORTION;
    var target_height = $(window).outerHeight(true) * COLOR_PICKER_HEIGHT_PROPORTION;
    
    if(target_height>target_width){
        target_height=target_width;
    }else{
        target_width=target_height;
    }
	
    //Create colour picker
	var raspiledColorPicker = new iro.ColorPicker("#raspiled-color-picker", {
      // Set the size of the color picker UI
      width: target_width,
      height: target_height,
      // Set the initial color
      color: current_hex
	});
	$.colour_picker = raspiledColorPicker; //Store in global namespace
	$.colour_picker.suppress_set = false; //Flag so we know whether to trigger ajax response or not
	
	//Bind ajax event to it
	//Handle events (these trigger AJAX calls to the same domain)
    var $current_colour_board = $(".current-colour");  
    raspiledColorPicker.on("color:change", function(color, changes) {
        if(!$.colour_picker.suppress_set){ //Sometimes we want to change the UI colour but not send a command to the Raspi
	    	$.fn.debounce( //Debounced to prevent excessive AJAX calls
	            $.ajax({
	                url: "/",
	                data: {"set": color.hexString},
	                success: function(data){
	                	update_current_colour(data["current"], data["current_rgb"], data["contrast"], false)
	                },
	                dataType: "json"
	            }),
	        250); //Debounce delay ms
        }
    });
	
	return raspiledColorPicker;
};
$.fn.extend({
    "debounce":debounce,
    "init_colourpicker": init_colourpicker
});

//Update the colour wheel
function update_current_colour(current, current_rgb, contrast, is_preset){
	//Updates the UI to show the specified colour
	is_preset = is_preset || false;
	
	//Colour label first
	var $current_colour_board = $("#current-colour");
    $current_colour_board.css("color",contrast);
    $current_colour_board.css("background-color", current);
    $current_colour_board.html(current + " " + current_rgb);
    
    //Now the colour wheel (we suppress this so we don't fire off a "set" ajax call:
	if(is_preset){ //Only need to move the wheel if its not a preset 
	    $.colour_picker.suppress_set = true;
		$.colour_picker.color.hexString = current;
		$.colour_picker.suppress_set = false;
	}
};

//Preset pickers:
$(document).ready(function(){
	$(".select_preset").on("click", function(e){
		var $picker_button = $(this);
		var $current_colour_board = $("#current-colour");
		var querystring = $picker_button.data("qs");
		//console.log(querystring)
                var colorstring = $picker_button.data("color");
		//console.log(colorstring)
		var is_sequence = $picker_button.data("sequence");
		$(".select_preset").removeClass("button_selected");
        $picker_button.addClass("button_selected");
		$.fn.debounce( //Debounced to prevent excessive AJAX calls
            $.ajax({
                url: "/?"+ querystring + '&' + colorstring,
                success: function(data){
                    //console.log(data);
                    update_current_colour(data["current"], data["current_rgb"], data["contrast"], true)
                },
                error: function(data){
                	$picker_button.addClass("button_selected_error");
                },
                dataType: "json"
            }),
	    150); //Debounce delay ms
            
	});
});

//Preset pickers:
$(document).ready(function(){
        $(".alarm_preset").on("click", function(e){
                var $m_option_selected = $(".Morning_select option:selected");
                var $d_option_selected = $(".Dawn_select option:selected");
                var m_querystring = $m_option_selected.data("qs");
                var m_colorstring = $m_option_selected.data("color");
                var m_is_sequence = $m_option_selected.data("sequence");
                var m_time = 'time=' + $('.morning-picker').val();
                var d_querystring = $d_option_selected.data("qs");
                var d_colorstring = $d_option_selected.data("color");
                var d_is_sequence = $d_option_selected.data("sequence");
                var d_time = 'time=' + $('.dawn-picker').val();
                $.fn.debounce( //Debounced to prevent excessive AJAX calls
                $.ajax({
                    url: "/?"+ m_querystring + '&' + d_querystring + '&' + m_colorstring + '&' + d_colorstring + '&' + m_is_sequence + '&' + d_is_sequence + '&' + m_time  +'&' + d_time,
                    success: function(data){
                    },
                    error: function(data){
                    },
                    dataType: "json"
                }),
            150); //Debounce delay ms

<<<<<<< HEAD
$(document).ready(function(){
    $("#alarm_button").on("click",function(e){
        var $alarm_button = $(this);
        var sunset_time = 'time=' + $(".dawn-picker").val()
        var sunrise_time = 'time=' + $(".morning-picker").val()
        var $sunrise_select = $(".Morning_select option:selected")
        var $sunset_select = $(".Dawn_select option:selected")
        var sunrise_querystring = $sunrise_select.data('qs')
        var sunset_querystring = $sunset_select.data('qs')
        var sunrise_colorstring = $sunrise_select.data("color");
        var sunset_colorstring = $sunset_select.data("color");
        var sunrise_is_sequence = $sunrise_select.data("sequence");
        var sunset_is_sequence = $sunset_select.data("sequence");
        $.fn.debounce( //Debounced to prevent excessive AJAX calls
        $.ajax({
                url: "/?"+ sunrise_querystring + '&' + sunset_querystring  + '&' + sunrise_colorstring + '&' + sunset_colorstring + '&' + sunrise_time + '&' + sunset_time,
                success: function(data){
                    console.log('SUCCESS');
                },
                error: function(data){
                    console.log('ERROR')
                },
                dataType: "json"
            }),
            150
        );
    });
});

=======
        });
});
>>>>>>> alarm

