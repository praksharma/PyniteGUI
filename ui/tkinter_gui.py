from tkinter import *
import random

root = Tk()
root.state("zoomed")    
root.title("Direct Stiffness")

test_label = Label(root, text="Test Label", font=("",35))
test_label.grid(row=0, column=0)

test_label = Label(root, text="Hello world")
test_label.grid(row=1, column=0)

## frame
test_frame = Frame(root)
test_frame.grid(row=2,column=0, padx=30, pady=30)
test_label2 = Label(test_frame, text="Hello frame")
test_label2.grid(row=0, column=0)

test_label3 = Label(test_frame, text="Hello frame")
test_label3.grid(row=1, column=0) 
def random_ints():
    test_label3.config(text= "Hello frame: " + str(random.randint(99999,1000000)))
## button
button_test = Button(root, text = "Button here", command=random_ints)
button_test.grid(row=3, column=3)

## entry boxes

text_box = Entry(root)
text_box.grid(row=6, column=0)
value =  text_box.get()

# checkbox

test_label4 = Label(test_frame, text="check box")
test_label4.grid(row=2, column=0) 
def check_toggle_message(status):
    test_label4.config(text="check box: " + str(status))

varCheck = StringVar()
varCheck.set("On")
check = Checkbutton(root, text="option 1", onvalue = "On", offvalue= "Off", variable=varCheck, command=lambda: check_toggle_message(varCheck.get()))
check.grid(row=7, column=0)


## sliders
frame_slider = Frame(root)
frame_slider.grid(row=8, column=0)

slider = Scale(frame_slider, orient="vertical")
slider.grid(row=0, column=0)


## radiobuttons
radio_frame = Frame(root)
radio_frame.grid(row=8, column=0)

colourmap = StringVar()
colourmap.set("jet")

radio_colour1 = Radiobutton(radio_frame, variable=colourmap, text="jet cmap", value="jet")
radio_colour2 = Radiobutton(radio_frame, variable=colourmap, text="plasma cmap", value="plasma")
radio_colour3 = Radiobutton(radio_frame, variable=colourmap, text="viridis cmap", value="viridis")
radio_colour4 = Radiobutton(radio_frame, variable=colourmap, text="tab10 cmap", value="tab10")

radio_colour1.grid(row=0, column =0)
radio_colour2.grid(row=1, column =0)
radio_colour3.grid(row=2, column =0)
radio_colour4.grid(row=3, column =0)




root.mainloop()