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
}

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
	                	update_current_colour(
                            data["current_hex"],
                            data["current_rgb_readable"] || data["current_rgb"],
                            data["contrast"],
                            false,
                            false,
                            "",
                            data["contrast"],  // Foreground
                            data["current_hex"]  // Background
                        )
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
function update_current_colour(current_hex, current_rgb_readable, contrast, is_preset, is_sequence, preset_or_sequence_name, foreground, background){
	//Updates the UI to show the specified colour
	is_preset = is_preset || false;
	preset_or_sequence_name = preset_or_sequence_name || null;
    foreground = foreground || contrast;
    background = background || current_hex;
	
	//Colour label first
	var $current_colour_board = $("#current-colour");
    if(is_sequence){
        $current_colour_board.css("color", foreground);
        $current_colour_board.css("text-shadow", "2px 2px 2px #000000");
        $current_colour_board.css("background-color", "");
        $current_colour_board.css("background", background);
    }else {
        $current_colour_board.css("color", foreground);
        $current_colour_board.css("text-shadow", "0 0 black");
        $current_colour_board.css("background", "");
        $current_colour_board.css("background-color", background);
    }
    if(preset_or_sequence_name){
        if(is_sequence) {
            $current_colour_board.html(preset_or_sequence_name);
        } else {
            $current_colour_board.html(preset_or_sequence_name + " " + current_rgb_readable);
        }
    } else {
        $current_colour_board.html(current_hex + " " + current_rgb_readable);
    }

    //Now the colour wheel (we suppress this so we don't fire off a "set" ajax call:
	if(is_preset){ //Only need to move the wheel if its not a preset
	    $.colour_picker.suppress_set = true;
        if(is_sequence){
            $.colour_picker.color.hexString = "#FFFFFF";
        } else {
            $.colour_picker.color.hexString = current_hex;
        }
		$.colour_picker.suppress_set = false;
	}
};

//Preset pickers:
$.fn.activate_presets = function(){
    $(document).on("click", ".select_preset", function(e){
		var $picker_button = $(this);
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
                        let foreground = $picker_button.css("color") || data["contrast"];
                        let background = $picker_button.css("background") || data["current_hex"];
                        update_current_colour(
                            data["current_hex"],
                            data["current_rgb"],
                            data["contrast"],
                            true,
                            true,
                            $picker_button.text(),
                            foreground,
                            background
                        )
                    } else {
                        // Not a sequence, so fill with the usual gradient and select the colour
                        $wheel_saturation.prop("fill", "url(#iroGradient0)");
                        $wheel_saturation.attr("fill", "url(#iroGradient0)");
                        let foreground = $picker_button.css("color") || data["contrast"];
                        let background = $picker_button.css("background-color") || data["current_hex"];
                        update_current_colour(
                            data["current_hex"],
                            data["current_rgb_readable"] || data["current_rgb"],
                            $picker_button.css("color") || data["contrast"],
                            true,
                            false,
                            $picker_button.text(),
                            foreground,
                            background
                        )
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





