# pip install sortedcontainers
# run this in the home folder : python setup.py build_ext --inplace
# read this for more cython tutorial (https://cython.readthedocs.io/en/latest/src/tutorial/cython_tutorial.html)
# http://ucam-smt.github.io/sgnmt/html/setup.html
# http://ucam-smt.github.io/sgnmt/html/tutorial_pytorch.html#tutorial-pytorch-label

# The file in swor/string_kernel_utils.py is used to construct the the kernel matrix
# The function in sowr/utils.py select_with_fast_greedy_map_inference is used to extract the submatrix (the topk choices)