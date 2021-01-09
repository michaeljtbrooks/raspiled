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
	    	let $wheel_saturation = $(document).find("circle.iro__wheel__saturation").first();
            $.fn.debounce( //Debounced to prevent excessive AJAX calls
                $.ajax({
	                url: "/",
	                data: {"set": color.hexString},
	                success: function(data){
	                    $wheel_saturation.prop("fill", "url(#iroGradient0)")
                        $wheel_saturation.attr("fill", "url(#iroGradient0)")
	                	update_current_colour(data["current_hex"], data["current_rgb"], data["contrast"], false)
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
function update_current_colour(current, current_rgb, contrast, is_preset, sequence_name){
	//Updates the UI to show the specified colour
	is_preset = is_preset || false;
	sequence_name = sequence_name || null;
	
	//Colour label first
	var $current_colour_board = $("#current-colour");
    $current_colour_board.css("color",contrast);
    $current_colour_board.css("background-color", current);
    if(sequence_name){
	    $current_colour_board.html(sequence_name);
    } else {
        $current_colour_board.html(current + " " + current_rgb);
    }

    //Now the colour wheel (we suppress this so we don't fire off a "set" ajax call:
	if(is_preset){ //Only need to move the wheel if its not a preset
	    $.colour_picker.suppress_set = true;
        if(sequence_name){
            $.colour_picker.color.hexString = "#FFFFFF";
        } else {
            $.colour_picker.color.hexString = current;
        }
		$.colour_picker.suppress_set = false;
	}
};

//Preset pickers:
$.fn.activate_presets = function(){
    $(document).on("click", ".select_preset", function(e){
		var $picker_button = $(this);
		var $current_colour_board = $("#current-colour");
		var querystring = $picker_button.data("qs");
        var colorstring = $picker_button.data("color");
		var is_sequence = $picker_button.data("sequence");
		let $wheel_saturation = $(document).find("circle.iro__wheel__saturation").first();
		$(".select_preset").removeClass("button_selected");
        $picker_button.addClass("button_selected");
		$.fn.debounce( //Debounced to prevent excessive AJAX calls
            $.ajax({
                url: "/?"+ querystring + '&' + colorstring,
                success: function(data, textStatus, xhr){
                    console.log(data);
                    if(is_sequence){
                        // Is a sequence. So set the wheel to show the gradient of the preset:
                        update_current_colour(data["current_hex"], data["current_rgb"], data["contrast"], true, $picker_button.text())
                    } else {
                        // Not a sequence, so fill with the usual gradient and select the colour
                        $wheel_saturation.prop("fill", "url(#iroGradient0)")
                        $wheel_saturation.attr("fill", "url(#iroGradient0)")
                        update_current_colour(data["current_hex"], data["current_rgb"], data["contrast"], true, false)
                    }
                },
                error: function(data){
                	$picker_button.addClass("button_selected_error");
                },
                dataType: "json"
            }),
	    150); //Debounce delay ms

	});
}
$(document).ready(function(){
    $.fn.activate_presets();
});





