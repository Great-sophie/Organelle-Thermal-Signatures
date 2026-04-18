Organelle Thermal Signatures

This repository contains Python scripts and tools for analyzing organelle-specific thermal signatures using membrane-camouflaged upconversion nanothermometers. The project focuses on uncovering the thermal characteristics of cancer metabolism at the subcellular level to advance our understanding of metabolic shifts in cancer cells.

Overview

The scripts in this repository are designed to process thermal data, align organelle-specific images (such as those of mitochondria, ER, and Golgi apparatus), and calculate the temperature of these organelles based on fluorescence intensity ratios. The temperature is calculated using the 525/545 fluorescence intensity ratio, where the 525/545 ratio is related to temperature through an in situ calibration curve. This project leverages upconversion nanothermometers to map temperature variations in live cancer cells and explore cellular metabolism.

Key Features
Fluorescence Ratio Calibration: Calibration of temperature using the 525/545 fluorescence ratio for organelles such as mitochondria, the endoplasmic reticulum (ER), and the Golgi apparatus.
Tri-Channel Image Registration: Registers and aligns thermal images from the 525 nm and 545 nm channels to mitochondria, ER, and Golgi fluorescence images for accurate temperature mapping.
Temperature Calculation: The 525/545 fluorescence ratio is used to calculate the organelle-specific temperature using pre-established calibration curves for each organelle.
Data Visualization: Visualizes the thermal signatures and analyzes the temperature distributions within various cellular structures.
Statistical Analysis: Performs statistical tests to identify significant temperature changes across different conditions.
Scripts
Mito ER Golgi Tri-channel merge temperature.py: Merges images from the 525 nm and 545 nm channels and registers them with images of mitochondria, ER, and Golgi. Calculates the temperature maps for each organelle using the fluorescence ratio.
Mito ER Golgi l temperature.py: Analyzes and calculates temperature data for individual channels (mitochondria and ER) using the fluorescence ratio.
Fluorescence Ratio Temperature Calibration Curve.py: Generates calibration curves to relate fluorescence ratios (525/545) to temperatures for accurate thermal measurements in live cells.
Installation
Prerequisites:
Python 3.x
Required Python libraries: cv2, matplotlib, numpy, scipy, glob, os

To install the required dependencies, create a virtual environment and run:

pip install -r requirements.txt
Setting Up:

Clone the repository:

git clone https://github.com/Great-sophie/Organelle-Thermal-Signatures.git

Navigate into the repository directory:

cd Organelle-Thermal-Signatures
Run the scripts as needed for your analysis.
Usage

To run the individual scripts, simply execute them from the command line or within a Python environment.

Example command:

python "Mito ER Golgi Tri-channel merge temperature.py"

Each script processes the respective image files and outputs the temperature maps and related statistical results.

Data

Ensure that the thermal imaging data files are correctly organized and available in the designated folder paths as specified within each script. The image files should follow the format Temperature-525-GroupID.tif and Temperature-545-GroupID.tif.

Contributing

Feel free to fork the repository and submit a pull request if you would like to contribute improvements or fixes. Please make sure that any contributions align with the project's objectives and follow the established conventions for code style and documentation.

License

This project is licensed under the MIT License. See the LICENSE
 file for more details.

Let me know if you would like any further modifications or additions!
