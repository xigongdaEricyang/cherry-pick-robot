import functools


def sort_cmp(number1, number2):
    if number1 not in pr_sorted_list: 
      return 1
    if number2 not in pr_sorted_list:
      return -1
    pr1_index = pr_sorted_list.index(number1)
    pr2_index = pr_sorted_list.index(number2)
    if pr1_index < pr2_index:
        return -1
    if pr1_index > pr2_index:
        return 1
    return 0 

if __name__ == "__main__":
    pr_sorted_list = [13, 1, 5, 7, 4, 19]
    pr_list = [1, 5, 7, 13, 19, 8]
    print(sorted(pr_list, key=functools.cmp_to_key(sort_cmp)))
    # print(len(list(filter(lambda x: x == '10', arr))))

