#!/usr/bin/env python3

"""
SPDX-License-Identifier: GPL-2.0-or-later

Christian Chwala (IMK) <christian.chwala@kit.edu>
Tzvetomir Stoyanov <tz.stoyanov@gmail.com>
"""

import argparse, string, sys
import pandas as pd
import xarray as xr
import csv
import pycomlink as pycml
from datetime import datetime
from tqdm import tqdm

description="Calculate rainfall information from commercial microwave link (CML) data"

linkColumns = ['LonA', 'LonB', 'latA', 'latB', 
               'CarTer_Index', 'CarTer_rxFrequency', 'CarTer_txFrequency']
signalColumns = ['CarTer_Index', 'tx', 'rx', 't', 'date']
outPrefix='wet'
rainThreshold=0.8

class rainCalc:
    def __init__(self, links, signals, outName, outAll):
        self.load_links(links)
        self.load_signals(signals)
        self.outPrefix=outName
        self.outAll=outAll

    def load_signals(self, file):
        self.signals=pd.read_csv(file)
        for col in signalColumns:
            if not col in self.signals.columns:
                print("Invalid signals file", file, ": column", col, "is  missing")
                sys.exit(1)
        times=[]
        drows=[]
        corr=0
        for i, s in tqdm(self.signals.iterrows(), desc="Loading signals", total=len(self.signals)):
            try:
                float(s.rx)
                float(s.tx)
                int(s.CarTer_Index)
                times.append(int(datetime.strptime(s.date, '%Y-%m-%d %H:%M:%S').strftime("%Y%m%d%H%M%S")))
            except:
                drows.append(i)
                continue
            if s.t == -99:
                s.rx = s.rx*10
                s.tx = s.tx*10
                corr=corr+1
        if len(drows) > 0: 
            self.signals.drop(index=drows, inplace=True)
        self.signals['time']=times
        print("Loaded ", len(self.signals), "signals, invalid", len(drows),", adjusted", corr)
        
    def load_links(self, file):
        self.links = pd.read_csv(file)
        for col in linkColumns:
            if not col in self.links.columns:
                print("Invalid links file", file, ": column", col, "is missing")
                sys.exit(1)
        drows=[]
        for i, l in tqdm(self.links.iterrows(), desc="Loading links", total=len(self.links)):
            try:
                float(l.LonA)
                float(l.latA)
                float(l.LonB)
                float(l.latB)
                int(l.CarTer_Index)
                float(l.CarTer_rxFrequency)
                float(l.CarTer_txFrequency)
            except:
                drows.append(i)    
                continue
        if len(drows):
            self.links.drop(index=drows, inplace=True)
        print("Loaded ", len(self.links), "links, invalid", len(drows))

    def calc(self):
        self.links['length'] = pycml.spatial.helper.haversine(lon1=self.links.LonA,
                                                              lat1=self.links.latA,
                                                              lon2=self.links.LonB,
                                                              lat2=self.links.latB)
        ds_list = []
        for _, row in tqdm(self.links.iterrows(), desc="Preparing links", total=len(self.links)):
            ds_list.append(
                xr.Dataset(
                    coords={
                        'longitude0': row.LonA, 
                        'latitude0': row.latA,
                        'longitude1': row.LonB,
                        'latitude1': row.latB,
                        'frequency': ('sublink_id', [row.CarTer_rxFrequency/1e6, row.CarTer_txFrequency/1e6]),
                        'length': row.length,
                        'cml_id': row.CarTer_Index,
                        # not sure how the two sublinks are stored in metadata and data, hence, now using
                        # the rx and tx naming convention of the two frequencies, see above
                        'sublink_id': ('sublink_id', ['rx', 'tx']),
                        'pol': 'v',
                    },
                )
            )

        raw_data_dict = {}
        for cml_id, g in tqdm(self.signals.groupby(self.signals.CarTer_Index),
                              desc="Preparing signals", total=len(tqdm(self.links))):
            df_temp = g.set_index('time').sort_index()
            df_temp['rx'] = df_temp.rx.astype(float)
            if df_temp.rx.median() < -100:
                df_temp['rx'] = df_temp.rx/10.0
            raw_data_dict[cml_id] = df_temp
        print("raw data", len(raw_data_dict))
        cml_ids_to_remove = []
        for ds_cml in tqdm(ds_list, desc="Matching links and signals", total=len(ds_list)):
            try:
                df_temp = raw_data_dict[int(ds_cml.cml_id.values)]
            except KeyError:
                print(f'Could not find raw_data in dict for ID {int(ds_cml.cml_id.values)}')
                cml_ids_to_remove.append(int(ds_cml.cml_id.values))
                continue
            ds_cml['rsl'] = df_temp.rx.astype(float)
            ds_cml['tsl'] = df_temp.tx.astype(float)
            ds_cml['date'] = df_temp.date
        
        cml_ids_to_remove = cml_ids_to_remove + list(self.links.CarTer_Index[self.links.length==0].values)
        self.rain = []
        for ds_cml in ds_list:
            cml_id = int(ds_cml.cml_id.values)
            if cml_id in cml_ids_to_remove:
                continue
            self.rain.append(ds_cml)        

        print("Clean list:", len(self.rain), len(ds_list))

        for cml in self.rain:
            cml['tsl'] = cml.tsl.where(cml.tsl < 100.0)
            cml['tsl'] = cml.tsl.where(cml.tsl > -50.0)
            cml['rsl'] = cml.rsl.where(cml.rsl > -85.0)
            cml['trsl'] = cml.tsl - cml.rsl
       
        for cml in self.rain:
            cml['trsl'] = cml.trsl.interp(method='linear')

        for cml in tqdm(self.rain, desc="Calculating"):
            cml['wet'] = cml.trsl.rolling(time=60, center=True).std(skipna=False) > rainThreshold
            cml['wet_fraction'] = (cml.wet==1).sum() / len(cml.time)
            cml['baseline'] = pycml.processing.baseline.baseline_constant(
                trsl=cml.trsl, 
                wet=cml.wet, 
                n_average_last_dry=5,
            )
            cml['waa'] = pycml.processing.wet_antenna.waa_schleiss_2013(
                rsl=cml.trsl, 
                baseline=cml.baseline, 
                wet=cml.wet, 
                waa_max=2.2, 
                delta_t=1, 
                tau=15,
            )
            cml['A'] = cml.trsl - cml.baseline - cml.waa

            # Note that we set A < 0 to 0 here, but it is not strictly required for 
            # the next step, because calc_R_from_A sets all rainfall rates below 
            # a certain threshold (default is 0.1) to 0. Some people might want to
            # keep A as it is to check later if there were negative numbers.
            cml['A'].values[cml.A < 0] = 0
            cml['R'] = pycml.processing.k_R_relation.calc_R_from_A(
                            A=cml.A, L_km=float(cml.length), f_GHz=cml.frequency, pol=cml.pol)
    def dump_rain_csv(self, rain, fname):
        field=["latitude", "longitude", "time", "rain"]
        lat=(rain.latitude0+rain.latitude1)/2
        lon=(rain.longitude0+rain.longitude1)/2
        with open(fname, 'w', newline='') as file:
            w=csv.writer(file)
            w.writerow(field)
            for t,s in rain.groupby(rain.time):
                w.writerow([lat.values, lon.values, s.date.values, s.R.median().values])
    def dump(self):
        for r in tqdm(self.rain, desc="Writing output files", total=len(self.rain)):
            fname=self.outPrefix+str(r.cml_id.values)+'.csv'
            if self.outAll:
                r.to_dataframe().to_csv(fname)
            else:
                self.dump_rain_csv(r, fname)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('-l', '--links', nargs=1, dest='links',
        help="CSV file with links information, it must containt columns: "+", ".join(linkColumns))
    parser.add_argument('-s', '--signals', nargs=1, dest='signals',
        help="CSV file with singals level, it must containt columns: "+", ".join(signalColumns))
    parser.add_argument('-p', '--prefix', nargs='?', dest='prefix', default=outPrefix,
        help="Prefix of the output file, default is "+outPrefix)
    parser.add_argument('-d', '--detailed', default=False, action=argparse.BooleanOptionalAction, dest='all',
        help="Dump detailed results")

    args = parser.parse_args()
    if not args.links or not args.signals:
        print("No input files", file=sys.stderr, flush=True)
        sys.exit(1)
    rc = rainCalc(links=args.links[0], signals=args.signals[0], outName=args.prefix, outAll=args.all)
    rc.calc()
    rc.dump()
