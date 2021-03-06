import numpy as np
import pandas as pd
import datetime as dt
import pdb

import util 
util = reload(util)

def build_outcome_data(in_dir, out_fname):

	first_dialysis_cpt = pd.read_csv(in_dir + 'kidney_disease_first_dialysis_cpt.txt', sep='\t', dtype=str)
	first_kidney_transplant_cpt = pd.read_csv(in_dir + 'kidney_disease_first_kidney_transplant_cpt.txt', sep='\t', dtype=str)
	first_dialysis_icd9_proc = pd.read_csv(in_dir + 'kidney_disease_first_dialysis_icd9_proc.txt', sep='\t', dtype=str)
	first_kidney_transplant_icd9_proc = pd.read_csv(in_dir + 'kidney_disease_first_kidney_transplant_icd9_proc.txt', sep='\t', dtype=str)

	people = list(first_dialysis_cpt['person'].values)
	people += list(first_dialysis_icd9_proc['person'].values)
	people += list(first_kidney_transplant_cpt['person'].values)
	people += list(first_kidney_transplant_icd9_proc['person'].values)
	people = np.unique(people)

	data = pd.DataFrame({'person': people})
	data = pd.merge(data, first_dialysis_cpt, how='left', on='person')
	data = pd.merge(data, first_dialysis_icd9_proc, how='left', on='person')
	data = pd.merge(data, first_kidney_transplant_cpt, how='left', on='person')
	data = pd.merge(data, first_kidney_transplant_icd9_proc, how='left', on='person')

	data['first_kidney_failure'] = np.nan
	data = data.reset_index()
	for i in range(len(data)):
		ds = []
		if pd.isnull(data['first_kidney_transplant_cpt'].iloc[i]) == False:
			d = dt.datetime.strptime(data['first_kidney_transplant_cpt'].iloc[i], '%Y%m%d')
			ds.append(d)
		if pd.isnull(data['first_kidney_transplant_icd9_proc'].iloc[i]) == False:
			d = dt.datetime.strptime(data['first_kidney_transplant_icd9_proc'].iloc[i], '%Y%m%d')
			ds.append(d)
		if pd.isnull(data['first_dialysis_cpt'].iloc[i]) == False:
			d = dt.datetime.strptime(data['first_dialysis_cpt'].iloc[i], '%Y%m%d')
			ds.append(d)
		if pd.isnull(data['first_dialysis_icd9_proc'].iloc[i]) == False:
			d = dt.datetime.strptime(data['first_dialysis_icd9_proc'].iloc[i], '%Y%m%d')
			ds.append(d)

		data.loc[i, 'first_kidney_failure'] = dt.datetime.strftime(np.min(ds), '%Y%m%d')

	data = data[['person','first_kidney_failure']]
	data = data[data['first_kidney_failure'].isnull() == False]

	data.to_csv(out_fname, index=False, sep='\t')

	return data

def setup(demo_fname, outcome_fname, cohort_fname):

	demo = pd.read_csv(demo_fname, sep='\t', dtype={'person': str, 'gender': str, 'age': int})

	outcome_data = pd.read_csv(outcome_fname, sep='\t', dtype=str)
	assert len(outcome_data.columns) == 2
	assert outcome_data.columns[0] == 'person'
	outcome_colname = outcome_data.columns[1]
	outcome_data = outcome_data[(outcome_data[outcome_colname].isnull() == False) & (outcome_data[outcome_colname] != '')]
	outcome_data.columns = ['person','first_outcome']

	people = pd.read_csv(cohort_fname, sep='\t', dtype=str)
	assert people.columns[1] != 'person'
	stat_colname = people.columns[1]
	people = people[['person',stat_colname]]
	people = people[(people[stat_colname].isnull() == False) & (people[stat_colname] != '')]
	people['first_outcome'] = ''
	people = people[['person','first_outcome']]

	n = len(people)
	cohort_data = pd.merge(people, outcome_data, how='left', on='person')
	assert n == len(people)

	cohort_data['first_outcome'] = ''
	cohort_data['first_outcome'] = cohort_data['first_outcome_y'] 
	cohort_data = cohort_data[['person','first_outcome']]
	cohort_data['first_outcome'][cohort_data['first_outcome'].isnull()] = ''

	n = len(cohort_data) 	
	cohort_data = pd.merge(cohort_data, demo, on='person')
	assert n == len(cohort_data)
	cohort_data = cohort_data.reset_index()
	cohort_data = cohort_data[['person','first_outcome','age','gender']]

	assert type(cohort_data['person'].iloc[0]) == type('')
	assert type(cohort_data['first_outcome'].iloc[0]) == type('')
	assert type(cohort_data['age'].iloc[0]) == np.int64
	assert type(cohort_data['gender'].iloc[0]) == type('') 

	return cohort_data
	 
def build_training_data(db, cohort_data, disease_loincs, lab_lower_bound=None, lab_upper_bound=None, \
	training_window_days=12*30, buffer_window_days=3*30, outcome_window_days=12*30, time_period_days=None, time_scale_days=30, \
	gap_days=None, calc_gfr=False, verbose=False, \
	progression=False, progression_lab_lower_bound=None, progression_lab_upper_bound=None, progression_gap_days=None, progression_init_stages=None, progression_stages=None, progression_diff_outcome=False, debug=False):

	disease_loinc_index_set = set([db.code_to_index['loinc'][code] for code in disease_loincs])

	data_min_date = dt.datetime.strptime(db.data_paths['min_date'], '%Y%m%d')
	data_max_date = dt.datetime.strptime(db.data_paths['max_date'], '%Y%m%d')
	first_outcome_col = 'first_outcome'

	training_data = {}
	training_data['person'] = []
	training_data['y'] = []
	training_data['training_start_date'] = []
	training_data['training_end_date'] = []
	training_data['outcome_start_date'] = []
	training_data['outcome_end_date'] = []
	training_data['age'] = []
	training_data['gender'] = []

	if progression:
		training_data['stage_x'] = []
		training_data['stage_y'] = []
		training_data['kf_x'] = []
		training_data['kf_y'] = []
	
	lab_data = {}
	lab_data['person'] = []
	lab_data['date'] = []
	lab_data['value'] = []
	lab_data['code'] = []
	
	for i in range(len(cohort_data)):
		if verbose == True:
			print i

		if debug:
			if i == 10000:
				break

		# Get patient data

		person = cohort_data['person'].iloc[i]
		age = cohort_data['age'].iloc[i]
		gender = cohort_data['gender'].iloc[i]
		is_female = (gender == 'F')

		first_outcome_date_str = cohort_data[first_outcome_col].iloc[i]
		if first_outcome_date_str == '':
			first_outcome_date = dt.datetime.max
		else:
			first_outcome_date = dt.datetime.strptime(cohort_data[first_outcome_col].iloc[i], '%Y%m%d')

		# Get lab data

		obs_db = db.db['loinc'][person]
		val_db = db.db['loinc_vals'][person]

		date_strs = obs_db[0]
		dates = map(lambda x: dt.datetime.strptime(x, '%Y%m%d'), date_strs)

		obs_M = obs_db[1]
		val_M = val_db[1]

		if len(date_strs) == 0:
			nz = (np.array([]), np.array([]))
		else:
			nz = obs_M.nonzero()

		nz_date_indices = nz[0]
		nz_code_indices = nz[1]

		# Find lab dates

		lab_dates = []
		lab_values = []
		lab_codes = []

		for d, date_index in enumerate(nz_date_indices):
			code_index = nz_code_indices[d]
			# Is the code for a date in the code list?
			if (code_index in disease_loinc_index_set) == True:
				date = dates[date_index]
				if obs_M[date_index, code_index] == 1 and val_M[date_index, code_index] > 0: 
					code = db.codes['loinc'][code_index]	
					val = val_M[date_index, code_index]

					if calc_gfr == True:	
						if code == '2160-0':
							val = util.calc_gfr(val, age, is_female)
					
					if val > 0:
						lab_codes.append(code)	
						lab_dates.append(date)
						lab_values.append(val)	

		labs = sorted(zip(lab_dates, lab_codes, lab_values), key=lambda x: x[0]) 
		lab_dates = np.array([l[0] for l in labs])
		lab_codes = np.array([l[1] for l in labs])
		lab_values = np.array([l[2] for l in labs])

		for l in range(len(lab_dates)):
			lab_data['person'].append(person)
			lab_data['date'].append(lab_dates[l])
			lab_data['code'].append(lab_codes[l])
			lab_data['value'].append(lab_values[l])			

		if (progression == True) and (progression_diff_outcome == False):

			stage_map = {} 
			date_map = {}
			onset_date_map = {}
			has_onset = False
			for plb in range(len(progression_lab_upper_bound)):
				for d, date in enumerate(lab_dates):
					if lab_values[d] < progression_lab_upper_bound[plb]:
						if stage_map.has_key(plb) == False:
							stage_map[plb] = 0
							date_map[plb] = lab_dates[d]
							onset_date_map[plb] = lab_dates[d]
						else:
							stage_map[plb] += (lab_dates[d] - date_map[plb]).days
							date_map[plb] = lab_dates[d]
	
						if (stage_map[plb] >= progression_gap_days) and ((plb in progression_stages) == True):
							onset_date = onset_date_map[plb]
							has_onset = True
							break
					else:
						stage_map.pop(plb, None)
						date_map.pop(plb, None)
						
				if has_onset == True:
					break

		elif (progression == True) and (progression_diff_outcome == True):

			stage_map = {} 
			date_map = {}
			onset_date_map = {}
			stage_onset_date_map = {}
			for plb in range(len(progression_lab_upper_bound)):
				for d, date in enumerate(lab_dates):
					if lab_values[d] < progression_lab_upper_bound[plb]:
						if stage_map.has_key(plb) == False:
							stage_map[plb] = 0
							date_map[plb] = lab_dates[d]
							onset_date_map[plb] = lab_dates[d]
						else:
							stage_map[plb] += (lab_dates[d] - date_map[plb]).days
							date_map[plb] = lab_dates[d]
	
						if (stage_map[plb] >= progression_gap_days):
							if stage_onset_date_map.has_key(plb) == False:
								stage_onset_date_map[plb] = onset_date_map[plb]
					else:
						stage_map.pop(plb, None)
						date_map.pop(plb, None)
			
		if time_period_days is not None:

			# Find time periods of dense observations

			training_start_dates = []

			if len(lab_dates) >= 2:	

				min_date = np.min(lab_dates)
				for t0 in range(len(lab_dates)):
					all_days = np.array(map(lambda x: (x - lab_dates[t0]).days, lab_dates))
					days = np.unique(all_days[all_days >= 0]) 
					is_consecutive = True
					for start_day, end_day in zip(range(0, training_window_days, time_period_days), range(time_period_days, training_window_days + time_period_days, time_period_days)):
						if np.sum((days >= start_day) & (days < end_day)) == 0:
							is_consecutive = False
							break
					
					if is_consecutive == True:
						date = min_date + dt.timedelta(days=int(time_scale_days*np.floor(((lab_dates[t0] - min_date).days)/float(time_scale_days))))
						training_start_dates.append(date)

				training_start_dates = np.unique(training_start_dates)

			training_start_dates = np.array(training_start_dates)

		else:
			
			training_start_dates = np.unique(lab_dates)

		# Build examples

		for training_start_date in training_start_dates:
			
			training_end_date = training_start_date + dt.timedelta(days=training_window_days)
			outcome_start_date = training_end_date + dt.timedelta(days=buffer_window_days)
			outcome_end_date = outcome_start_date + dt.timedelta(days=outcome_window_days)

			# Doesnt have outcome in training window?

			doesnt_have_outcome_in_training_window = (first_outcome_date >= outcome_start_date)
	
			# Has the condition in the training window?

			if progression == False:	

				lab_dates_low = [date for d, date in enumerate(lab_dates) \
					 if lab_values[d] >= lab_lower_bound and lab_values[d] < lab_upper_bound and lab_dates[d] >= training_start_date and lab_dates[d] < training_end_date]
				if len(lab_dates_low) > 0:
					if gap_days is not None:
						diff = (np.max(lab_dates_low) - np.min(lab_dates_low)).days
						if diff >= gap_days:
							has_condition_in_training_window = True
						else:
							has_condition_in_training_window = False
					else:
						has_condition_in_training_window = True
				else:
					has_condition_in_training_window = False

			# Collect data 

			if progression:

				if progression_diff_outcome:
					eligible = (training_start_date >= data_min_date) and (outcome_end_date < data_max_date)
				else:
					if has_onset:
						doesnt_have_onset_in_training_window = (onset_date >= outcome_start_date)
					else:	
						doesnt_have_onset_in_training_window = True

					eligible = (doesnt_have_onset_in_training_window == True) and (training_start_date >= data_min_date) and (outcome_end_date < data_max_date)
	
				if eligible:

					# training

					stage_x_person = -1

					stage_map = {} 
					date_map = {}
					for plb in range(len(progression_lab_upper_bound)):
						for d, date in enumerate(lab_dates):
							if lab_dates[d] >= training_start_date and lab_dates[d] < training_end_date:
								if lab_values[d] < progression_lab_upper_bound[plb]:
									if stage_map.has_key(plb) == False:
										stage_map[plb] = 0
										date_map[plb] = lab_dates[d]
									else:
										stage_map[plb] += (lab_dates[d] - date_map[plb]).days
										date_map[plb] = lab_dates[d]
								else:
									stage_map.pop(plb, None)
									date_map.pop(plb, None)

					for plb in range(len(progression_lab_upper_bound)):
						if stage_map.has_key(plb):
							if stage_map[plb] >= progression_gap_days:
								stage_x_person = plb

					# outcome

					stage_y_person = -1

					stage_map = {}
					date_map = {}
					outcome_stage_map = {}
					for plb in range(len(progression_lab_upper_bound)):
						for d, date in enumerate(lab_dates):
							if lab_dates[d] >= outcome_start_date and lab_dates[d] < outcome_end_date:
								if lab_values[d] < progression_lab_upper_bound[plb]:
									if stage_map.has_key(plb) == False:
										stage_map[plb] = 0
										date_map[plb] = lab_dates[d]
									else:
										stage_map[plb] += (lab_dates[d] - date_map[plb]).days
										date_map[plb] = lab_dates[d]
								else:
									if stage_map.has_key(plb):
										if outcome_stage_map.has_key(plb) == False:
											outcome_stage_map[plb] = stage_map[plb]
										else:
											if stage_map[plb] > outcome_stage_map[plb]:
												outcome_stage_map[plb] = stage_map[plb]
	
									stage_map.pop(plb, None)
									date_map.pop(plb, None)

					for plb in range(len(progression_lab_upper_bound)):
						if outcome_stage_map.has_key(plb):	
							if outcome_stage_map[plb] >= progression_gap_days:
								stage_y_person = plb

					# add row
				
					if progression_diff_outcome:
						doesnt_have_stage_onset_in_training_window = True
						if (stage_x_person < stage_y_person) and (stage_x_person != -1) and (stage_y_person != -1):
							if stage_onset_date_map[stage_y_person] < outcome_start_date:
								doesnt_have_stage_onset_in_training_window = False
						add_row = ((stage_x_person in progression_init_stages) == True) and ((stage_y_person in progression_stages) == True) and (doesnt_have_stage_onset_in_training_window == True)
					else:
						add_row = (stage_x_person in progression_init_stages) == True

					if add_row:

						if doesnt_have_outcome_in_training_window:
							kf_x_person = 0
						else:
							kf_x_person = 1
	
						if first_outcome_date < outcome_end_date:
							kf_y_person = 1
						else:	
							kf_y_person = 0	

						if progression_diff_outcome:
								if (stage_x_person < stage_y_person):
									y_person = 1
								else:
									y_person = 0
						else:
							if has_onset == True:
								if (onset_date >= outcome_start_date) and (onset_date < outcome_end_date):
									y_person = 1
								else:
									y_person = 0
							else:
								y_person = 0
											
						training_data['person'].append(person)
						training_data['stage_x'].append(stage_x_person)
						training_data['stage_y'].append(stage_y_person)
						training_data['kf_x'].append(kf_x_person)
						training_data['kf_y'].append(kf_y_person)
						training_data['y'].append(y_person)
						training_data['training_start_date'].append(dt.datetime.strftime(training_start_date, '%Y%m%d'))
						training_data['training_end_date'].append(dt.datetime.strftime(training_end_date, '%Y%m%d'))
						training_data['outcome_start_date'].append(dt.datetime.strftime(outcome_start_date, '%Y%m%d'))
						training_data['outcome_end_date'].append(dt.datetime.strftime(outcome_end_date, '%Y%m%d'))
						training_data['age'].append(age)
						training_data['gender'].append(gender)

			else:
				if doesnt_have_outcome_in_training_window == True and has_condition_in_training_window == True and training_start_date >= data_min_date and outcome_end_date < data_max_date:
			
					if first_outcome_date < outcome_end_date:
						y_person = 1
					else:	
						y_person = 0	
					
					training_data['person'].append(person)
					training_data['y'].append(y_person)
					training_data['training_start_date'].append(dt.datetime.strftime(training_start_date, '%Y%m%d'))
					training_data['training_end_date'].append(dt.datetime.strftime(training_end_date, '%Y%m%d'))
					training_data['outcome_start_date'].append(dt.datetime.strftime(outcome_start_date, '%Y%m%d'))
					training_data['outcome_end_date'].append(dt.datetime.strftime(outcome_end_date, '%Y%m%d'))
					training_data['age'].append(age)
					training_data['gender'].append(gender)

	training_data = pd.DataFrame(training_data)

	return training_data	
