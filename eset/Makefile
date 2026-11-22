INCLUDE = ./
SRD_H = parser.h common.h script_formatter.h
SRC = main.c parser.c common.c script_formatter.c
TARGET = eset
CC = gcc

$(TARGET) : $(SRC) $(SRD_H)
	$(CC) -o ${TARGET} -I$(INCLUDE) $(SRC)
