import os

from os import path
from wordcloud import WordCloud
import sqlite3


# get data directory (using getcwd() is needed to support running example in generated IPython notebook)
# d = path.dirname(__file__) if "__file__" in locals() else os.getcwd()

# Read the whole text.
# text = open(path.join(d, 'constitution.txt')).read()


conn = sqlite3.connect("../../data/nume-strazi/strazi-ro.db")
cursor = conn.cursor()
query = 'SELECT Artera, COUNT(Artera) as Counter from RSV_AEP_21 GROUP by Artera ORDER by Counter DESC limit 100'
cursor.execute(query)
rows = cursor.fetchall()

for row in rows:
    print(row)

text = "ala bala porptocala portocala ala portocala laba bala ion popescu ion ionescu"
# Generate a word cloud image
wordcloud = WordCloud().generate(text)

# Display the generated image:
# the matplotlib way:
import matplotlib.pyplot as plt

plt.imshow(wordcloud, interpolation="bilinear")
plt.axis("off")

# lower max_font_size
wordcloud = WordCloud(max_font_size=40).generate(text)
plt.figure()
plt.imshow(wordcloud, interpolation="bilinear")
plt.axis("off")
plt.show()

# The pil way (if you don't have matplotlib)
# image = wordcloud.to_image()
# image.show()