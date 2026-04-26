import os
import csv
from PIL import Image
import numpy as np
import matplotlib.pyplot as plt
from os import path
from wordcloud import WordCloud
# import sqlite3

# source_csv='../../data/nume-strazi/strazi-ro-freq1.csv'
source_csv='../../data/nume-strazi/strazi-freq2.csv'
# maskpng = '../assets/strazi-wordcloud-2.png'
maskpng = '/Users/procopiu/Sites/python-toolbench/statistics/nume-strazi/assets/strazi-wordcloud-2.png'
dx = path.dirname(__file__) if "__file__" in locals() else os.getcwd()


reader = csv.reader(open(source_csv, 'r',newline='\n'))
d = {}

for k,v in reader:
  d[k] = float(v)
zemask = np.array(Image.open(path.join(dx, maskpng)))
# Generate a word cloud image
wordcloud = WordCloud(mask=zemask, width = 1400, height = 980, background_color=None, mode = 'RGBA', relative_scaling = 0.75, font_path = '/Users/procopiu/Library/Fonts/RobotoCondensed-Bold.ttf')

wordcloud.generate_from_frequencies(d) 

# store to file
wordcloud.to_file(path.join(dx, "alice.png"))

# show
plt.imshow(wordcloud, interpolation='bilinear')
plt.axis("off")
plt.figure()
plt.imshow(zemask, cmap=plt.cm.gray, interpolation='bilinear')
plt.axis("off")
plt.show()

 # Display the generated image:
# the matplotlib way:
# plt.figure()
# plt.imshow(wordcloud, interpolation="bilinear")
# plt.axis("off")
# plt.show()

# The pil way (if you don't have matplotlib)
# image = wordcloud.to_image()
# image.show()