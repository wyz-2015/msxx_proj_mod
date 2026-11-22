#include "common.h"

bool feof_(FILE* restrict inFile) // 是否到达文件结尾
{
	int cTest = fgetc(inFile); // 试取字

	if (cTest != EOF) {
		ungetc(cTest, inFile); // 若不是则放回流中，甚至可以是stdin
		return false;
	} else {
		return true;
	}
}
