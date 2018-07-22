<script type="text/javascript">
 $(document).ready(function(){{
   $.getJSON( "https://api.sunrise-sunset.org/json?lat={latcoord}&lng={loncoord}&date=today",{{tags: "sunrise sunset", 
        tagmode: "any", 
        format: "json" 
     }}).done(function( data ) {{
 //        console.log(data)
         sunrise=data.results.astronomical_twilight_end;
         sunset =data.results.astronomical_twilight_begin;
         $(".Morning").append('<input type="Morning Alarm" class="form-control morning-picker" value="'+sunrise.split(":")[0]+':'+sunrise.split(":")[1]+'" >')
         $('.Dawn').append('<input type="Dawn Alarm" class="form-control dawn-picker" value="'+sunset.split(":")[0]+':'+sunset.split(":")[1]+'">') 
 
     new Picker(document.querySelector('.morning-picker'), {{
         format: 'HH:mm',
         text: {{ 
            title: 'Morning', 
            cancel: 'Cancel', 
            confirm: 'Confirm', 
         }} 
     }}); 
 
     new Picker(document.querySelector('.dawn-picker'), {{ 
         format: 'HH:mm', 
         text: {{ 
            title: 'Dawn', 
            cancel: 'Cancel', 
            confirm: 'Confirm', 
         }} 
     }}); 
    }}) 
  }}) 
</script> 
