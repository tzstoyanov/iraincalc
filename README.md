# iRainCalc

## Overview
Calculate rainfall information from commercial microwave link (CML) data,
using the [pycomlink](https://github.com/pycomlink/pycomlink) library.

## Try it out

### Prerequisites
- Linear Algebra Libraries, installed on your OS - [BLAS](https://www.netlib.org/blas/)
  and [LAPACK](https://www.netlib.org/lapack/). Follow these instructions
  for Linux, or look for instructions specific to your OS in internet:

  Debian: `sudo apt install libblas3 liblapack3 liblapack-dev libblas-dev`

  Fedora: `sudo dnf install blas blas-devel lapack lapack-devel`

- Tested with Python 3.9 and 3.10.

### Get the code
```
git clone https://github.com/tzstoyanov/iraincalc
```

### Create virtual environment and install dependencies
```
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
### Prepare you data
Input parameters of the program are two CSV files, describing links and
measured data. The links file describes a set of `AB` links and must have
these mandatory rows:
 - `CarTer_Index` - Index of the link.
 - `LonA` and `latA` - Coordinates of the A point of the link.
 - `LonB` and `latB` - Coordinates of the B point of the link.
 - `CarTer_rxFrequency` - Receiving frequency.
 - `CarTer_txFrequency` - Transmitting  frequency.

The data file describes the power of the received and transmitted signal
for each link at given time. The file must have these mandatory rows:
 - `CarTer_Index` - Index of the link. This must correspond with the link
   index from the links file.
 - `tx` - Transmitting power.
 - `rx` - Receiving power.
 - `t` - 
 - `date` - date and time of this measurement in format `YYYY-MM-DD hh:mm:ss`,
where `YYYY` is the year, `MM` is the month, `DD` is the day, `hh` is the
hour, `mm` are minutes and `ss` are seconds.

### Run the calculations
Make directory for the output files:
- `mkdir out`

Run the program with your data:
- `./iraincalc.py -l <links>.csv -s <data>.csv -p ./out/`

A set of csv files will be generated in the `out/` directory, one for each
link. Each file has these rows:
 - `latitude` and `longitude` - Coordinates of the link.
 - `time` - Time of the measurement.
 - `rain` - Calculated rain.

## License
iRainCalc is available under the [GPLv2.0 or later license](LICENSE).
