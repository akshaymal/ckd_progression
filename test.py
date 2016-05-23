import shelve
import numpy as np
import pandas as pd
import scipy.sparse
import os
import tables

import util
util = reload(util)

import run
run = reload(run)

tests_dir = 'tests/'
soln_dir = tests_dir + 'soln/'

def add_person(db, codes, person, dates, data, code_indices, date_indices):

	X = scipy.sparse.csr_matrix((data, (date_indices, code_indices)), shape=(len(dates), len(codes)), dtype=np.float64)
	db[person] = (dates, X)

	return db

def create_demographics(people, tests_dir):

	ages = [20,40,80,65,42,25,75,70,60,55]
	genders = ['M','F','M','M','F','M','F','F','F','M']

	data = {}
	data['person'] = []
	data['age'] = []
	data['gender'] = []
	demographics_fname = tests_dir + 'test_demographics.txt'
	with open(demographics_fname, 'w') as fout:
		for i in range(len(people)):
			data['person'].append(people[i])
			data['age'].append(ages[i])
			data['gender'].append(genders[i])
	data = pd.DataFrame(data)
	data[['age','gender','person']].to_csv(tests_dir + 'test_demographics.txt', index=False, sep='\t')

	return data

def create_db():
	
	cpt_db_fname = tests_dir + 'test_cpt_person_to_code.db'
	loinc_db_fname = tests_dir + 'test_loinc_person_to_code.db'
	loinc_vals_db_fname = tests_dir + 'test_loinc_vals_person_to_code.db'
	cpt_list_fname = tests_dir + 'test_cpt_list.txt'
	icd9_proc_list_fname = tests_dir + 'test_icd9_proc_list.txt'
	icd9_proc_db_fname = tests_dir + 'test_icd9_proc_person_to_code.db'
	loinc_list_fname = tests_dir + 'test_loinc_list.txt'
	people_list_fname = tests_dir + 'test_people_list.txt'

	cpts = util.read_list_files(cpt_list_fname)
	loincs = util.read_list_files(loinc_list_fname)
	people = util.read_list_files(people_list_fname)
	icd9_procs = util.read_list_files(icd9_proc_list_fname)

	loinc_db = shelve.open(loinc_db_fname)
	loinc_vals_db = shelve.open(loinc_vals_db_fname)
	cpt_db = shelve.open(cpt_db_fname)
	icd9_proc_db = shelve.open(icd9_proc_db_fname)

	for person in people:
		cpt_db[person] = (np.array([], dtype=object), scipy.sparse.csr_matrix(([], ([],[])), dtype=np.bool, shape=(0, len(cpts))))		
		loinc_vals_db[person] = (np.array([], dtype=object), scipy.sparse.csr_matrix(([], ([],[])), dtype=np.float64, shape=(0, len(loincs))))		
		loinc_db[person] = (np.array([], dtype=object), scipy.sparse.csr_matrix(([], ([],[])), dtype=np.bool, shape=(0, len(loincs))))
		icd9_proc_db[person] = (np.array([], dtype=object), scipy.sparse.csr_matrix(([], ([],[])), dtype=np.bool, shape=(0, len(icd9_procs))))

	# 437 = 01990 (kidney transplant), 5779 = 50380 (kidney transplant), 5 = 00099 (not a kidney transplant)
	cpt_db = add_person(cpt_db, cpts, people[0], np.array(['20110102','20100101','20121015'], dtype=object), [1,1,1], [437,5779,5], [1,0,2])
	pd.DataFrame({'person': [people[0]], 'first_kidney_transplant_cpt': ['20100101']}).to_csv(soln_dir + 'first_kidney_transplant_cpt.txt', index=False, sep='\t')

	# 1182 = 3942 (dialysis)
	icd9_proc_db = add_person(icd9_proc_db, icd9_procs, people[0], np.array(['20090504', '20090401'], dtype=object), [1,1], [1182, 1182], [0, 1]) 
	pd.DataFrame({'person': [people[0]], 'first_dialysis_icd9_proc': ['20090401']}).to_csv(soln_dir + 'first_dialysis_icd9_proc.txt', index=False, sep='\t')

	pd.DataFrame({'person': [], 'first_dialysis_cpt': []}).to_csv(soln_dir + 'first_dialysis_cpt.txt', index=False, sep='\t')
	pd.DataFrame({'person': [], 'first_kidney_transplant_icd9_proc': []}).to_csv(soln_dir + 'first_kidney_transplant_icd9_proc.txt', index=False, sep='\t')

	# 3225 = 33914-3 (GFR), 4026 = 48642-3 (GFR), 4027 = 48643-1 (GFR), 1909 = 2160-0 (Creatinine)
	loinc_db = add_person(loinc_db, loincs, people[0], np.array(['20100101','20110101'], dtype=object), [1, 1, 1], [3225,4026,4027], [0, 1, 1])
	loinc_vals_db = add_person(loinc_vals_db, loincs, people[0], np.array(['20100101','20110101'], dtype=object), [30, 16, 40], [3225,4026,4027], [0, 1, 1])

	loinc_db = add_person(loinc_db, loincs, people[1], np.array(['20100101','20100501'], dtype=object), [1, 1], [3225,4026], [0, 1])
	loinc_vals_db = add_person(loinc_vals_db, loincs, people[1], np.array(['20100101','20100501'], dtype=object), [25, 18], [3225,4026], [0, 1])

	pd.DataFrame({'person': [people[0], people[1]], 'min_gfr': [16.0, 18.0], 'age': [20, 40], 'gender': ['M', 'F']}).to_csv(soln_dir + 'min_gfr.txt', index=False, sep='\t')
	pd.DataFrame({'person': [people[1]], 'n_gap_stage45': [2]}).to_csv(soln_dir + 'n_gap_stage45.txt', index=False, sep='\t')

	loinc_db.close()
	loinc_vals_db.close()
	cpt_db.close()
	icd9_proc_db.close()

def assert_equals(a, b):
	assert len(a.columns) == len(b.columns)
	assert (np.sort(a.columns.values) == np.sort(b.columns.values)).all()
	assert len(a) == len(b)
	for col in a.columns:
		assert (a[col].values == b[col].values).all() 

def test():

	create_db()

	out_dir = tests_dir + 'kidney_disease/'
	test_data_paths_fname = tests_dir + 'test_data_paths.yaml'
	test_stats_list_fname = tests_dir + 'test_stats.yaml'
	stats_key = 'test_kidney_disease'
	demographics_fname = 'tests/test_demographics.txt'
	outcome_stat_name = 'first_dialysis'
	cohort_stat_name = 'n_gap_stage45'

	run.run(out_dir, test_data_paths_fname, test_stats_list_fname, stats_key, check_if_file_exists=False, verbose=False)

	test_soln_fnames = []
	test_soln_fnames.append(('test_kidney_disease_first_dialysis_cpt.txt', 'first_dialysis_cpt.txt'))
	test_soln_fnames.append(('test_kidney_disease_first_kidney_transplant_cpt.txt', 'first_kidney_transplant_cpt.txt'))
	test_soln_fnames.append(('test_kidney_disease_first_dialysis_icd9_proc.txt', 'first_dialysis_icd9_proc.txt'))
	test_soln_fnames.append(('test_kidney_disease_first_kidney_transplant_icd9_proc.txt', 'first_kidney_transplant_icd9_proc.txt'))
	test_soln_fnames.append(('test_kidney_disease_min_gfr.txt', 'min_gfr.txt'))
	test_soln_fnames.append(('test_kidney_disease_n_gap_stage45.txt', 'n_gap_stage45.txt'))

	for test_fname, soln_fname in test_soln_fnames:
		a = pd.read_csv(out_dir + test_fname, sep='\t', dtype=str)
		b = pd.read_csv(soln_dir + soln_fname, sep='\t', dtype=str)
		assert_equals(a, b)



