<img width="1199" height="749" alt="img-to-spooker_eL8573OGfu" src="https://github.com/user-attachments/assets/b21706bb-6a21-472d-bc2c-1f78b0164cd0" />


# img-to-spooker

A tool built in python to take an image containing a shape that fits the following condition and converts it into a spooker table

* A single enclosed shape with no voids or crossing edges

The tool will probably break and complain if it doesn't satisfy those requirements, if you have any issues, DM me on discord (@alphawuff)

## Output format

A list of x,y pairs of coordinates scaled to fit in the 3x3 field of the spooker table generator available at https://spooker-table-generator.tiiny.site/:

e.g.
```
0.1234,0.5678
0.2345,0.6789
...
```
I tried to match the vertex count to the way the table generator likes, but I was guessing a little bit at how they implemented it, idk if it'll be perfect.

Any vertex order issues can be fixed within the table generator itself by just clicking "Auto-Fix Point Order" near the top of the generator, next to the validation button.

## What is "resolution"?

Resolution (default 24) just specifies how many vertices you want the output table to have. 
Lower values may truncate curves, higher values may cause tables to take longer for the generator (or devs) to parse.
Try and find the lowest value that conserves the general shape of your table

Custom values are supported by manual typing input. The slider stays within the recommended vertex count range (8 to 48)


## GUI

Pretty self explanatory. Load an image at the top left, enter a desired vertex resolution, then hit convert. The online generator can be opened for conversion to a JSON format so the devs can utilize the table. Copy to clipboard copies the full output vertex list for pasting into the online too.
