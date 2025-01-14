# -*- coding=utf-8 -*-
# library: jionlp
# author: dongrixinyu
# license: Apache License 2.0
# email: dongrixinyu.89@163.com
# github: https://github.com/dongrixinyu/JioNLP
# description: Preprocessing tool for Chinese NLP


import re
import pdb
import numpy as np

from jionlp import logging
from jionlp.rule.prompt import *
from jionlp.rule.rule_pattern import GRADING_NUM_PATTERN
from jionlp.gadget.money_parser import MoneyParser


class MELLM(object):
    """ MELLM algorithm, short for Mutual Evaluation of Large Language Model,
    which is an auto method to evaluate several LLMs.

    This evaluation algorithm applies EM algorithm to achieve the final result.


    Args:
        llm_names(list[str]): all the names of llms,
            such as chatgpt-3.5, 文心一言, skywork, gpt4, llama-7B, etc.


    Returns:
        dict[str,float]: scores of all llms.

    Examples:
        >>> import jionlp as jio
        >>> text = '喀左旗覃家岗街道梨树湾村芭蕉沟村民小组临.222号'
        >>> res = jio.parse_location(text)
        >>> print(res)

    """
    def __init__(self, llm_names, llm_apis, exam_questions, self_grading=True):
        """ preparation before applying mellm.

        Args:
            llm_names(list[str]): all the names of llms,
                such as chatgpt-3.5, 文心一言, skywork, gpt4, llama-7B, etc.
            llm_apis: all the apis for llms in accordence with the sequence of llm_names
            exam_questions(list[dict]): all the questions of the exam,
                you can get it from `jio. ...`
            self_grading(bool): llm grade for itself.

        """
        self.llm_names = llm_names
        self.llm_num = len(self.llm_names)
        self.llm_names_dict = dict([(i, idx) for idx, i in enumerate(self.llm_names)])

        self.llm_apis = llm_apis

        # responses from llms answering questions from the given exam.
        self.llm_answers_to_questions = dict([(i, {}) for i in self.llm_names])
        """an example of self.llm_answers_to_questions
        {
            'chatgpt3.5': {
                0: 'A,B,C',
                1: '英国是正确答案',
                2: '从前有一个小孩子...'
            },
            'llama': {
                0: 'A,B is correct',
                1: '英国才是正确答案',
                2: '从前，有两个小孩子...'
            },
            'ChatGLM': {
                0: 'A,D',
                1: 'Italy 是正确的',
                2: '很久很久以前...'
            }
        }
        """

        # responses from llms giving scores for other models.
        self.llm_answers_to_grades = dict([(i, dict([(j, {}) for j in self.llm_names if i != j]))
                                           for i in self.llm_names])
        """an example of self.llm_answers_to_grades
        {
            'chatgpt3.5': {
                'llama': {
                    0: '2分',
                    1: '1分',
                    2: '4.5 分'      
                },
                'ChatGLM': {
                    0: '1',
                    1: '1.5',
                    2: '4 分' 
                }
            },
            'llama': {
                'chatgpt3.5': {
                    0: '2 分',
                    1: '这个答案可以得2分',
                    2: '5分。'
                },
                'ChatGLM': {
                    0: '1分',
                    1: '1.5。',
                    2: '5分。' 
                }
            },
            'ChatGLM': {
                ...
            }
        }
        """
        self.llm_answers_to_norm_grades = dict([(i, dict([(j, {}) for j in self.llm_names if i != j]))
                                                for i in self.llm_names])

        # all the questions
        self.exam_questions = exam_questions
        self.question_num = len(self.exam_questions)

        # to store all the moves when calling llm-apis
        self.storage_info = {}

        self.num_convertor = MoneyParser()
        self.grading_score_pattern = re.compile(GRADING_NUM_PATTERN)

        # numpy arrays for computing
        self.grading_matrix = None
        self.llm_average_scores = np.zeros((self.llm_num, self.question_num))
        self.weight_matrix = np.ones((self.llm_num, )) / self.llm_num
        self.total_score = np.zeros((self.llm_num, ))
        self.llm_variance = np.zeros((self.llm_num,))

        self.learning_rate = 0.2

    def answer_questions(self):
        """let llm answer questions from the given exam.

        each question has 'score', 'question_type', 'question', 'correct_answer',
        'correct_answer' may not exist for some questions. So these questions
        should be mutually evaluated by mellm.

        Args:

        Returns:
            None
        """

        for llm, llm_api in zip(self.llm_names, self.llm_apis):
            for idx, question_item in enumerate(self.exam_questions):

                # call the api to get result
                # all exceptions which might occur should be handled by the api itself.
                result = llm_api(question_item['question'])
                self.llm_answers_to_questions[llm].update({idx: result})

        # save all the result into file.

        for llm, llm_api in zip(self.llm_names, self.llm_apis):
            # llm will grade for other models' answer
            for _llm in self.llm_names:
                # _llm means models to be graded
                if _llm == llm:
                    # not grading itself
                    continue

                for idx, question_item in enumerate(self.exam_questions):

                    # grade another llms' exam
                    answer_result = self.llm_answers_to_questions[_llm][idx]
                    if 'correct_answer' not in question_item:
                        score = question_item['score']
                        question = question_item['question']
                        _input = GRADING_CHINESE_PROMPT_WITHOUT_CORRECT_ANSWER.format(
                            question, answer_result, score)
                    else:
                        score = question_item['score']
                        question = question_item['question']
                        correct_answer = question_item['correct_answer']
                        _input = GRADING_CHINESE_PROMPT_WITH_CORRECT_ANSWER.format(
                            question, correct_answer, answer_result, score)

                    grading_result = llm_api(_input)
                    self.llm_answers_to_grades[llm][_llm].update({idx: grading_result})

    def normalize_grading_result(self):
        """ normalize grading results from `4 分`, `四分。`, `4.` to `4`

        Returns:
            float: the score get from the result.

        """
        for llm in self.llm_names:
            for _llm in self.llm_names:
                if _llm == llm:
                    continue

                for idx, _ in enumerate(self.exam_questions):
                    grading_result = self.llm_answers_to_grades[llm][_llm][idx]
                    grading_score = self.grading_score_pattern.search(grading_result)

                    res_num = self.money_parser(grading_score, ret_format='str')
                    if res_num is None:
                        raise ValueError('the model `{}` gives a invalid score to model `{}` at `{}`'.format(
                            llm, _llm, idx))
                    else:
                        norm_score = float(res_num[:-1])
                        self.llm_answers_to_norm_grades[llm][_llm].update({idx: norm_score})

    def norm_test(self, grading_result):
        # when handling 四点五, this function should separate the string into two parts by char 点
        grading_score = self.grading_score_pattern.search(grading_result)
        if grading_score is None:
            raise ValueError('grading_result `{}` is invalid.'.format(grading_result))

        res_num = self.num_convertor(grading_score.group(), ret_format='str')
        if res_num is None:
            print(res_num, grading_score)
        else:
            norm_score = float(res_num[:-1])
            print(norm_score)

    def build_grading_matrix(self):
        self.grading_matrix = np.zeros((self.llm_num, self.llm_num, self.question_num))

        for llm in self.llm_names:
            for _llm in self.llm_names:
                if _llm == llm:
                    continue

                for idx, _ in enumerate(self.exam_questions):
                    self.grading_matrix[llm][_llm][idx] = self.llm_answers_to_norm_grades[llm][_llm][idx]

    def run(self, grading_matrix):
        self.grading_matrix = grading_matrix

        while True:
            for _idx_llm in range(self.llm_num):
                for idx_question in range(self.question_num):

                    # get the average score for _llm,
                    # which can be treated as the true score that _llm get
                    average_result = self.grading_matrix[:, _idx_llm, idx_question]
                    average_result = np.dot(self.weight_matrix, average_result)
                    # this may be changed
                    average_result = round(average_result * 2) / 2
                    self.llm_average_scores[_idx_llm][idx_question] = average_result

            # compute total_score
            for _idx_llm in range(self.llm_num):
                self.total_score[_idx_llm] = sum(self.llm_average_scores[_idx_llm])
            print(self.total_score)

            # compute the variance of each llm
            for idx_llm in range(self.llm_num):
                diff = self.grading_matrix[idx_llm] - self.llm_average_scores

                self.llm_variance[idx_llm] = (diff * diff).sum()

            # update weight
            weight_matrix_1 = (1 / self.llm_variance) / (1 / self.llm_variance).sum()
            # the llm with poorest preformence does not grade other models.
            weight_matrix_2 = self.total_score - self.total_score.min()
            weight_matrix_2 = weight_matrix_2 / weight_matrix_2.sum()

            self.weight_matrix = (weight_matrix_1 + weight_matrix_2) / 2
            print(self.weight_matrix)
            print()
