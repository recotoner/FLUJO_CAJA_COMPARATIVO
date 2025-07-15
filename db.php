<?php

        class DB{

                private $host;
                private $db;
                private $user;
                private $password;
                private $charset;

                public function __construct(){
                        $this->host = 'www.hrubilar.cl';
                        $this->db = 'chr72164_retail';
                        $this->user = 'chr72164_hrubilar';
			$this->password = 'master2010';
                        //$this->user = '';
                        //$this->password = '';
                        $this->charset = 'utf8';
                }

                        function connect(){

                                try{

                                        //$connection = "mysql:host=".$this->host.";dbname=" . $this->db . ";charset=" .$this->charset;
                                        $connection = "mysql:host=".$this->host.";dbname=" . $this->db . ";charset=" .$this->charset;
                                      $options = [
                                                PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
                                                PDO::ATTR_EMULATE_PREPARES => false,
                                        ];
                                        $pdo = new PDO($connection, $this->user, $this->password);

                                        return $pdo;

                                }catch(PDOException $e){
                                        print_r('Error connection: ' . $e->getMessage());
                                }

                        }
        }


?>
